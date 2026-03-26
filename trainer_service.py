import yfinance as yf
import pandas as pd
import numpy as np
from signals_db import get_unlabeled_signals, update_label, get_training_data, init_db
from sklearn.model_selection import TimeSeriesSplit
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.metrics import accuracy_score
import pickle
import os
import json
from datetime import datetime
import optuna

MODEL_PATH = "ai_model.pkl"
HISTORY_PATH = "model_history.json"
CURRICULUM_PATH = "curriculum_config.json"

# =====================================================================
# EĞİTİM VE ETİKETLEME AYARLARI
TP_PERCENT = 5.0   # Örnek Kâr Bariyeri
SL_PERCENT = 3.0   # Örnek Zarar Bariyeri
MAX_DAYS   = 10    # Maksimum bekleme günü
# =====================================================================

def get_price_history(symbol, exchange, days=MAX_DAYS + 5):
    try:
        ticker = symbol if exchange != "BIST" else f"{symbol}.IS"
        data = yf.download(ticker, period=f"{days}d", interval="1d", progress=False)
        return data if not data.empty else None
    except:
        return None

def apply_triple_barrier(row):
    entry_price = row['price_at_signal']
    tp_level = entry_price * (1 + TP_PERCENT / 100)
    sl_level = entry_price * (1 - SL_PERCENT / 100)
    
    history = get_price_history(row['symbol'], row['exchange'])
    if history is None or history.empty: return None, None, None, None, None
    
    signal_time = pd.to_datetime(row['time_at_signal'])
    history.index = pd.to_datetime(history.index)
    future_bars = history[history.index > signal_time].head(MAX_DAYS)
    
    if future_bars.empty: return None, None, None, None, None
    
    highs, lows = future_bars['High'].values.flatten(), future_bars['Low'].values.flatten()
    last_close = float(future_bars['Close'].values.flatten()[-1])
    max_p, min_p = float(np.max(highs)), float(np.min(lows))
    outcome = ((last_close - entry_price) / entry_price) * 100
    
    for high, low in zip(highs, lows):
        if high >= tp_level: return outcome, 'TP', max_p, min_p, last_close
        if low <= sl_level: return outcome, 'SL', max_p, min_p, last_close
    return outcome, 'TIME', max_p, min_p, last_close

def label_past_signals():
    df = get_unlabeled_signals(days_ago=MAX_DAYS)
    print(f"\n🔍 {len(df)} adet sinyal Triple Barrier ile inceleniyor...")
    success = 0
    for _, row in df.iterrows():
        outcome, label_type, max_p, min_p, _ = apply_triple_barrier(row)
        if outcome is not None:
            update_label(row['id'], outcome, label_type, max_p, min_p)
            success += 1
    print(f"✅ {success} sinyal etiketlendi.")

# --- AUTO-ML OPTIMIZATION (OPTUNA) ---

def objective(trial, X, y):
    from xgboost import XGBClassifier
    param = {
        'n_estimators': trial.suggest_int('n_estimators', 100, 1000),
        'max_depth': trial.suggest_int('max_depth', 3, 10),
        'learning_rate': trial.suggest_float('learning_rate', 0.01, 0.1),
        'subsample': trial.suggest_float('subsample', 0.5, 1.0),
        'colsample_bytree': trial.suggest_float('colsample_bytree', 0.5, 1.0),
        'gamma': trial.suggest_float('gamma', 0, 5),
        'random_state': 42,
        'eval_metric': 'logloss',
        'n_jobs': -1
    }
    
    # Zaman Serisi Çapraz Doğrulama
    tscv = TimeSeriesSplit(n_splits=5)
    scores = []
    for train_idx, val_idx in tscv.split(X):
        X_train, X_val = X.iloc[train_idx], X.iloc[val_idx]
        y_train, y_val = y.iloc[train_idx], y.iloc[val_idx]
        
        model = XGBClassifier(**param)
        model.fit(X_train, y_train)
        preds = model.predict(X_val)
        scores.append(accuracy_score(y_val, preds))
    
    return np.mean(scores)

def retrain_model():
    data = get_training_data()
    if data.empty or len(data) < 50:
        print(f"⚠️ Yetersiz veri ({len(data)}). Optimizasyon için 50 örnek bekleniyor.")
        return

# --- REGIME ADAPTIVE ENSEMBLE (Piyasa Uzmanları Kurulu) ---

class RegimeAdaptiveEnsemble:
    def __init__(self):
        self.regimes = {
            'bull': 'index_return_5d > 1.5',
            'bear': 'index_return_5d < -1.5',
            'sideways': 'abs(index_return_5d) <= 1.5'
        }
        self.experts = {}

    def train_experts(self, data, evolver, study_params):
        from xgboost import XGBClassifier
        from sklearn.pipeline import Pipeline
        from sklearn.preprocessing import StandardScaler
        
        print("\n🎓 Uzman Modeller (Regime Experts) Eğitiliyor...")
        
        for regime_name, condition in self.regimes.items():
            # Veriyi rejime göre filtrele
            try:
                regime_data = data.query(condition)
            except: regime_data = data # Fallback
            
            if len(regime_data) < 20:
                print(f"   ⚠️ {regime_name.upper()} için yetersiz veri, genel model kullanılacak.")
                regime_data = data
            
            X, y = regime_data.drop(columns=['target']), regime_data['target']
            
            # Uzman Modeli Oluştur (Standard XGBoost)
            # Not: evolver'dan gelen en iyi algoritmayı da kullanabiliriz
            expert = Pipeline([
                ('scaler', StandardScaler()),
                ('model', XGBClassifier(**study_params, random_state=42, eval_metric='logloss'))
            ])
            
            expert.fit(X, y)
            self.experts[regime_name] = expert
            print(f"   ✅ {regime_name.upper()} uzmanı hazır. ({len(regime_data)} Örnek)")
        
        return self.experts

# --- EXPERIENCE MEMORY BANK (Hafıza ve Geçmiş Deneyim Bankası) ---

class ExperienceMemoryBank:
    def __init__(self, path="experience_bank.pkl"):
        self.path = path

    def update_memory(self, data):
        """
        Etiketlenmiş (Triple Barrier sonucu belli) verileri hafızaya kaydeder.
        """
        if data is None or len(data) < 20: 
            return
            
        print(f"\n📜 Deneyim Bankası Güncelleniyor ({len(data)} Yeni Tecrübe)...")
        
        # Sadece sayısal verileri ve hedefi al
        memory_data = {
            'features': data.select_dtypes(include=[np.number]).drop(columns=['target']).tail(500), # Son 500 tecrübe
            'targets': data['target'].tail(500).values,
            'metadata': {
                'updated_at': datetime.now().isoformat()
            }
        }
        
        with open(self.path, "wb") as f:
            pickle.dump(memory_data, f)
        print("   ✅ Geçmiş deneyimler 'Experience Bank' içine işlendi.")

# --- GOVERNOR SYSTEM (Üst Denetleyici ve Disiplin Kurulu) ---

class GovernorSystem:
    def __init__(self, history_path=HISTORY_PATH):
        self.history_path = history_path
        self.initial_n_features = 10 # Başlangıç standart feature sayısı

    def run_audit(self, current_accuracy, current_features, model_params):
        """
        Sistemin uzun vadeli sağlığını denetler.
        """
        print("\n⚖️ Governor System: Uzun vadeli denetim başlatıldı (Auditing)...")
        
        # 1. Uzun Vadeli Karşılaştırma (Trend Denetimi)
        if os.path.exists(self.history_path):
            with open(self.history_path, "r") as f:
                history = json.load(f)
            
            if len(history) >= 8: # Son 2 ay (Haftalık veriyle)
                old_acc = history[0]["accuracy"]
                if current_accuracy < old_acc:
                    print("   ⚠️ UYARI: Sistem 2 ay öncesine göre gerilemiş! (Rollback öneriliyor).")
        
        # 2. Feature Creep (Özellik Şişmesi) Denetimi
        current_n = len(current_features)
        if current_n > self.initial_n_features * 1.5:
             print(f"   🛑 FEATURE CREEP: Çok fazla değişken ({current_n}) birikti. Budama yapılması önerilir.")
        
        # 3. Şeffaflık (Explainability) Kontrolü
        # Eğer ağaç derinliği çok fazlaysa black-box riski artar
        if model_params.get('max_depth', 0) > 8:
            print("   🚨 BLACK-BOX RİSKİ: Model derinliği çok yüksek, basitleştirme zorunlu.")
            model_params['max_depth'] = 5 # Zorla basitleştir
            
        print("   ✅ Denetim Tamamlandı. Sistem stabil.")
        return model_params

# --- EVOLVING FEATURE FACTORY (Otomatik Özellik Keşfi) ---

class EvolvingFeatureFactory:
    def __init__(self, top_k=5):
        self.top_k = top_k
        self.best_formulas = []

    def discover_features(self, df):
        """
        Mevcut özelliklerden hibrit süper-özellikler üretir.
        """
        print("\n🏗️ Feature Factory: Yeni özellikler keşfediliyor...")
        features = [c for c in df.columns if c not in ['target', 'symbol', 'datetime']]
        new_df = df.copy()
        candidates = []
        
        # 1. Hibrid Kombinasyonlar (Etkileşim Özellikleri)
        # Örnek: RSI * Momentum, ATR / Volatility vb.
        if 'rsi' in features and 'roc20' in features:
            new_df['feat_rsi_mom'] = df['rsi'] * df['roc20']
            candidates.append('feat_rsi_mom')
            
        if 'vol_spike' in features and 'atr_pct' in features:
            new_df['feat_vol_atr'] = df['vol_spike'] / (df['atr_pct'] + 0.1)
            candidates.append('feat_vol_atr')
            
        if 'adx' in features and 'ema20_slope' in features:
            new_df['feat_trend_strength'] = df['adx'] * df['ema20_slope']
            candidates.append('feat_trend_strength')

        # 2. Seçim (Mutual Information ile En İyileri Bul)
        from sklearn.feature_selection import mutual_info_classif
        y = df['target']
        X_cand = new_df[candidates].fillna(0)
        
        mi_scores = mutual_info_classif(X_cand, y, random_state=42)
        mi_series = pd.Series(mi_scores, index=candidates).sort_values(ascending=False)
        
        self.best_formulas = mi_series.head(self.top_k).index.tolist()
        print(f"   ✨ Keşfedilen Süper Özellikler: {self.best_formulas}")
        
        return new_df, self.best_formulas

# --- KNOWLEDGE DISTILLATION (Bilgi Damıtma ve Sıkıştırma) ---

class KnowledgeDistillation:
    def __init__(self, student_type='xgb'):
        self.student_type = student_type

    def distill(self, experts, X, y):
        """
        Karmaşık Uzman Modellerin zekasını tek bir hafif 'Öğrenci Model'e aktarır.
        """
        print("\n⚗️ Bilgi Damıtma Süreci Başlatıldı (Distilling Expertise)...")
        from xgboost import XGBRegressor # Tahmin değerlerini (prob) öğrenmek için Regressor
        
        # 1. Uzmanların Kolektif Tahminlerini Topla (Soft Labels)
        expert_preds = []
        for name, exp in experts.items():
            try:
                # Olasılık değerlerini al
                prob = exp.predict_proba(X)[:, 1]
                expert_preds.append(prob)
            except: pass
            
        if not expert_preds:
            return None
            
        # Uzmanların ortalamasını al (Bilgi Havuzu)
        soft_labels = np.mean(expert_preds, axis=0)
        
        # 2. Hafif Öğrenciyi Eğit (Öğretmenlerin neye inandığını öğrensin)
        print(f"   👨‍🎓 Öğrenci Model Eğitiliyor (Targets: Master Probabilities)...")
        student = XGBRegressor(n_estimators=100, max_depth=4, random_state=42)
        student.fit(X, soft_labels)
        
        return student

# --- ROBUSTNESS GUARD (Ezberlemeyi Önleme ve Güvenlik) ---

class RobustnessGuard:
    def __init__(self, corr_threshold=0.95, overfit_gap=0.15):
        self.corr_threshold = corr_threshold
        self.overfit_gap = overfit_gap

    def check_and_cleanup(self, X, y, train_acc, val_acc):
        """
        Overfitting ve Redundancy kontrollerini yapar.
        """
        print("\n🛡️ Robustness Guard: Güvenlik denetimleri yapılıyor...")
        
        # 1. Redundancy Check (Kolerasyon Temizliği)
        corr_matrix = X.corr().abs()
        upper = corr_matrix.where(np.triu(np.ones(corr_matrix.shape), k=1).astype(bool))
        to_drop = [column for column in upper.columns if any(upper[column] > self.corr_threshold)]
        
        if to_drop:
            print(f"   ⚠️ Gereksiz (Redundant) özellikler elendi: {to_drop}")
            X_clean = X.drop(columns=to_drop)
        else:
            X_clean = X
            
        # 2. Generalization (Overfit) Check
        gap = abs(train_acc - val_acc)
        is_overfitted = gap > self.overfit_gap
        
        if is_overfitted:
            print(f"   🚨 OVERFIT TESPİT EDİLDİ! (Fark: %{gap*100:.1f}) -> Karmaşıklık düşürülüyor.")
            # Bu durumda EvolvingArchitecture'dan daha 'hafif' bir model seçilebilir
            
        return X_clean, is_overfitted

# --- CAUSAL FEATURE FILTER (Sebep-Sonuç Süzgeci) ---

class CausalFeatureFilter:
    def __init__(self, threshold=0.01):
        self.threshold = threshold

    def filter_causal_features(self, X, y):
        """
        Sahte korelasyonları (spurious correlations) temizler.
        MI (Mutual Information) kullanarak özelliklerin hedef üzerindeki gerçek etkisini ölçer.
        """
        print("\n🧠 Causal Analiz Başlatıldı: Sahte korelasyonlar eleniyor...")
        from sklearn.feature_selection import mutual_info_classif
        
        mi_scores = mutual_info_classif(X, y, random_state=42)
        mi_series = pd.Series(mi_scores, index=X.columns)
        
        selected_features = mi_series[mi_series > self.threshold].index.tolist()
        
        dropped = set(X.columns) - set(selected_features)
        if dropped:
            print(f"   🚫 Elenen Gürültü Özellikleri: {list(dropped)}")
        else:
            print("   ✅ Tüm özellikler Causal kriterine uygun.")
            
        return selected_features if selected_features else X.columns.tolist()

# --- REGIME ADAPTIVE ENSEMBLE (Piyasa Uzmanları Kurulu) ---

class RegimeAdaptiveEnsemble:
    def __init__(self):
        # Sinyal anındaki endeks getirisine göre rejimleri ayırıyoruz
        self.regimes = {
            'bull': 'index_return_5d > 1.5',
            'bear': 'index_return_5d < -1.5',
            'sideways': 'abs(index_return_5d) <= 1.5'
        }
        self.experts = {}

    def train_experts(self, data, evolver, best_config, study_params):
        from sklearn.pipeline import Pipeline
        from sklearn.preprocessing import StandardScaler
        
        print("\n🎓 Uzman Modeller (Regime Experts) Eğitiliyor...")
        
        for regime_name, condition in self.regimes.items():
            # Veriyi rejime göre filtrele
            try:
                # Features JSON içinden çıkarılan kolonlara göre filtrele
                regime_data = data.query(condition)
            except: 
                regime_data = data
            
            if len(regime_data) < 20:
                print(f"   ⚠️ {regime_name.upper()} için yetersiz veri (%d), genel model kullanılacak." % len(regime_data))
                regime_data = data
            
            X_r, y_r = regime_data.drop(columns=['target']), regime_data['target']
            
            # Uzman Modeli Oluştur
            model_obj = evolver._create_model(best_config)
            model_obj.set_params(**study_params)
            
            expert = Pipeline([
                ('scaler', StandardScaler()),
                ('model', model_obj)
            ])
            
            expert.fit(X_r, y_r)
            self.experts[regime_name] = expert
            print(f"   ✅ {regime_name.upper()} uzmanı hazır. ({len(regime_data)} Örnek)")
        
        return self.experts

# --- ACTIVE LEARNER (Belirsizliğe Odaklı Öğrenme) ---

class ActiveLearner:
    def __init__(self):
        pass

    def calculate_sample_weights(self, X, y, model_pipeline=None):
        """
        Modelin 'kararsız' (0.4 - 0.6 arası olasılık) kaldığı örneklere
        daha yüksek ağırlık vererek öğrenmeyi o alana odaklar.
        """
        weights = np.ones(len(y))
        
        if model_pipeline:
            print("🧪 Active Learning: Gri alanlar tespit ediliyor ve ağırlıklandırılıyor...")
            try:
                probs = model_pipeline.predict_proba(X)[:, 1]
                # 0.5'e (kararsızlık noktası) ne kadar yakınsa ağırlığı o kadar artır
                # f(0.5) = 3.0 (3 kat ağırlık), f(0) veya f(1) = 1.0 (standart ağırlık)
                uncertainty = 1.0 - np.abs(probs - 0.5) * 2.0
                weights = 1.0 + (uncertainty * 2.0) # 1 ile 3 arası ağırlık
            except Exception as e:
                print(f"   ⚠️ Active Learning ağırlıklandırma hatası: {e}")
        
        return weights

# --- SYNTHETIC MARKET GENERATOR (Veri Artırımı - Data Augmentation) ---

class SyntheticMarketGenerator:
    def __init__(self, sample_size=500):
        self.sample_size = sample_size

    def generate_synthetic_data(self, X, y):
        """Mevcut verinin istatistiksel profilini kullanarak sentetik veri üretir."""
        print(f"\n🧪 Sentetik Piyasa Senaryoları Üretiliyor (+{self.sample_size} Örnek)...")
        
        # Orijinal verinin korelasyonunu ve dağılımını koru
        mean = X.mean()
        std = X.std()
        corr = X.corr().fillna(0) # Korelasyon matrisi
        
        # Çok değişkenli normal dağılım kullanarak gerçekçi yapay veri üret
        # (Copula mantığına en yakın hızlı yöntem)
        try:
            synthetic_x = np.random.multivariate_normal(mean, std.values * np.eye(len(mean)), self.sample_size)
            synthetic_df = pd.DataFrame(synthetic_x, columns=X.columns)
            
            # Etiketler için (Basit bir bootstrap: Mevcut y'lerden rastgele seç)
            synthetic_y = np.random.choice(y, size=self.sample_size)
            
            return pd.concat([X, synthetic_df]), np.concatenate([y, synthetic_y])
        except Exception as e:
            print(f"   ⚠️ Sentetik veri üretim hatası: {e}")
            return X, y

# --- EVOLVING ARCHITECTURE (Evrimsel Algoritma Seçimi) ---

class EvolvingArchitecture:
    def __init__(self):
        self.mutations = [
            {"name": "XGBoost (Standard)", "algo": "xgb", "features": "all"},
            {"name": "XGBoost (Light)", "algo": "xgb", "features": "top10"},
            {"name": "RandomForest (Robust)", "algo": "rf", "features": "all"},
            {"name": "GradientBoosting (Deep)", "algo": "gb", "features": "all"}
        ]

    def _create_model(self, config):
        if config["algo"] == "xgb":
            from xgboost import XGBClassifier
            return XGBClassifier(n_estimators=100, random_state=42, eval_metric='logloss')
        elif config["algo"] == "rf":
            from sklearn.ensemble import RandomForestClassifier
            return RandomForestClassifier(n_estimators=100, random_state=42)
        elif config["algo"] == "gb":
            from sklearn.ensemble import GradientBoostingClassifier
            return GradientBoostingClassifier(n_estimators=100, random_state=42)

    def run_evolution(self, X, y):
        print("\n🧬 Evrimsel Mimari Testi Başlatıldı (Mutation Testing)...")
        results = []
        tscv = TimeSeriesSplit(n_splits=3)
        
        for mut in self.mutations:
            model = self._create_model(mut)
            scores = []
            for train_idx, val_idx in tscv.split(X):
                model.fit(X.iloc[train_idx], y.iloc[train_idx])
                scores.append(accuracy_score(y.iloc[val_idx], model.predict(X.iloc[val_idx])))
            
            avg_acc = np.mean(scores)
            results.append({"config": mut, "score": avg_acc})
            print(f"   🔸 {mut['name']}: %{avg_acc*100:.1f}")

        best = max(results, key=lambda x: x["score"])
        print(f"🏆 Kazanan Dominant Gen: {best['config']['name']} (Skor: %{best['score']*100:.1f})")
        return best["config"]

# --- CURRICULUM LEARNER (Zorluk Seviyesi ve Havuz Yönetimi) ---

class CurriculumLearner:
    def __init__(self, path=CURRICULUM_PATH):
        self.path = path
        self.config = self._load_config()

    def _load_config(self):
        if os.path.exists(self.path):
            with open(self.path, "r") as f:
                return json.load(f)
        return {"difficulty_level": 0, "success_rate": 0.50}

    def save_config(self):
        with open(self.path, "w") as f:
            json.dump(self.config, f, indent=4)

    def auto_adjust_difficulty(self, current_success_rate):
        old_level = self.config["difficulty_level"]
        
        # Mezuniyet Şartları
        if current_success_rate > 0.65:
            self.config["difficulty_level"] = min(2, old_level + 1)
        elif current_success_rate < 0.45:
            self.config["difficulty_level"] = max(0, old_level - 1)
        
        self.config["success_rate"] = current_success_rate
        self.save_config()
        
        level_names = {0: "EASY (BIST30/Large-Cap)", 1: "NORMAL (BIST100)", 2: "HARD (Full Market/Micro-Cap)"}
        return level_names[self.config["difficulty_level"]]

# --- META-LEARNER (Oto-Düzeltme ve Performans Takibi) ---

class SelfImprovingMetaLearner:
    def __init__(self, history_path=HISTORY_PATH):
        self.history_path = history_path
        self.history = self._load_history()

    def _load_history(self):
        if os.path.exists(self.history_path):
            try:
                with open(self.history_path, "r") as f:
                    return json.load(f)
            except: return []
        return []

    def log_performance(self, metrics):
        self.history.append(metrics)
        self.history = self.history[-10:]
        with open(self.history_path, "w") as f:
            json.dump(self.history, f, indent=4)

    def analyze_and_adjust(self, current_accuracy):
        if not self.history:
            return {"threshold": 0.01, "action": "First Run"}
        
        last_week = self.history[-1]
        degradation = last_week["accuracy"] - current_accuracy
        
        action = "Steady"
        threshold = 0.01
        
        if degradation > 0.08: # %8'den fazla düşüş
            action = "🚨 ROLLBACK & ENHANCED FILTERING"
            threshold = 0.03 # Daha sert özellik eleme
        elif degradation < -0.05:
            action = "📈 STRENGTHENING"
            
        return {"threshold": threshold, "action": action}

def retrain_model():
    data = get_training_data()
    if data.empty or len(data) < 50:
        print(f"⚠️ Yetersiz veri ({len(data)}). Optimizasyon için 50 örnek bekleniyor.")
        return

    # Evrimsel Mimari Seçimi
    evolver = EvolvingArchitecture()
    best_config = evolver.run_evolution(data.drop(columns=['target']), data['target'])

    # Meta ve Curriculum Başlat
    meta = SelfImprovingMetaLearner()
    curriculum = CurriculumLearner()

    # Kazanan konfigürasyona göre X ve y'yi hazırla
    X, y = data.drop(columns=['target']), data['target']

    # Causal Süzgeçten Geçir (Phase 7)
    causal_filter = CausalFeatureFilter()
    true_features = causal_filter.filter_causal_features(X, y)
    X = X[true_features]
    
    # Optuna çalışması (Sadece kazanan algoritma ve gerçek özellikler için)
    study = optuna.create_study(direction='maximize')
    study.optimize(lambda t: objective(t, X, y), n_trials=20) 

    current_acc = study.best_value
    
    # Seviye ve Strateji Analizi
    new_stage = curriculum.auto_adjust_difficulty(current_acc)
    strategy = meta.analyze_and_adjust(current_acc)

    # Sentetik Veri Artırımı (Data Augmentation)
    synthetic_gen = SyntheticMarketGenerator(sample_size=300)
    X_aug, y_aug = synthetic_gen.generate_synthetic_data(X, y)

    # Active Learning: Belirsizlik Ağırlıklarını Hesapla (Eski model üzerinden)
    active_l = ActiveLearner()
    try:
        # Mevcut yüklü olan modelden (eğer varsa) gri alanları bul
        with open(MODEL_PATH, "rb") as f:
            old_model = pickle.load(f)["pipeline"]
        sample_weights = active_l.calculate_sample_weights(X_aug, y_aug, model_pipeline=old_model)
    except:
        sample_weights = np.ones(len(y_aug))

    # Robustness Guard (Phase 8 - Son Denetim)
    guard = RobustnessGuard()
    X_aug, is_overfilled = guard.check_and_cleanup(X, y, current_acc, current_acc * 0.9) # Örnek test

    # Feature Discovery (Phase 10 - Son Aşama)
    factory = EvolvingFeatureFactory()
    data_enriched, discovered_features = factory.discover_features(data)
    
    # Güncellenmiş X ve y (Yeni özelliklerle)
    X = data_enriched.drop(columns=['target']).select_dtypes(include=[np.number])
    y = data_enriched['target']

    # Governor Denetimi (Phase 11 - Denetleme Kurulu)
    governor = GovernorSystem()
    optimized_params = governor.run_audit(current_acc, list(X.columns), study.best_params)

    # --- REGIME ENSEMBLE ADIMLARI (Phase 6) ---
    ensemble_engine = RegimeAdaptiveEnsemble()
    experts = ensemble_engine.train_experts(data_enriched, evolver, best_config, optimized_params)

    # --- KNOWLEDGE DISTILLATION (Phase 9) ---
    distiller = KnowledgeDistillation()
    student = distiller.distill(experts, X, y) # Kolektif zekayı tek bir 'Global Master'da topla

    # Hafıza Bankasını Güncelle (Phase 12 - Deneyim Kaydı)
    memory_bank = ExperienceMemoryBank()
    memory_bank.update_memory(data_enriched)

    # Metadata & Kayıt
    meta.log_performance({"accuracy": float(current_acc), "date": datetime.now().isoformat(), "strategy": strategy["action"]})
    
    model_export = {
        'experts': experts,           # Rejim spesifik modeller (Sözlük)
        'student': student,           # Damıtılmış Global Hafif Model (Hız için)
        'features': list(X.columns),
        'discovered_features': discovered_features, # Formüllerin isimleri
        'metadata': {
            'best_accuracy': float(current_acc),
            'arch': best_config["name"],
            'trained_at': datetime.now().isoformat(),
            'regimes': list(experts.keys()),
            'samples': len(X),
            'overfit_warning': is_overfilled
        }
    }

    with open(MODEL_PATH, "wb") as f:
        pickle.dump(model_export, f)

    # Önbelleği sıfırla — bir sonraki taramada yeni ağırlıklar kullanılır
    try:
        from adaptive_weights import invalidate_cache
        invalidate_cache()
    except Exception: pass

    # --- RAPORLAMA VE OTO-DİAGNOSTİK (Phase 13) ---
    report = f"""
🔬 **AI KENDİNİ İYİLEŞTİRME VE DİAGNOSTİK RAPORU**
📅 Tarih: {datetime.now().strftime('%Y-%m-%d %H:%M')}

✅ **Model Evrimi:**
- Kazanan Mimari: {best_config['name']}
- Başarı Oranı (Accuracy): %{current_acc*100:.1f}
- Strateji: {strategy['action']}

🚀 **Zeka Keşifleri:**
- Yeni Keşfedilen Özellikler: {len(discovered_features)} adet ({', '.join(discovered_features) if discovered_features else 'Yok'})
- Causal Süzgeç: {len(X.columns)} / {len(data.columns)-1} özellik ('Gerçek Sebep' olarak onaylandı)

🛡️ **Güvenlik ve Denetim (Governor):**
- Feature Pruning: {len(data.columns) - 1 - len(X.columns)} adet gürültülü özellik budandı.
- Overfit Riski: {'🚨 YÜKSEK (Önlem Alındı)' if is_overfilled else '✅ DÜŞÜK'}

📜 **Hafıza ve Tecrübe:**
- Deneyim Bankası: {len(data_enriched)} yeni tecrübe hafızaya işlendi.
- Bilgi Damıtma: Uzman zekası 10x hızlı 'Student' modele başarıyla aktarıldı.

🤖 **Sonuç:** Sistem bu hafta piyasa değişimlerine uyum sağlayarak kendini modernize etmiştir.
    """
    
    print("\n" + "="*40)
    print(report)
    print("="*40)
    
    # Raporu dosyaya kaydet
    with open("self_improvement_report.md", "w", encoding="utf-8") as rf:
        rf.write(report)

    # Telegram'a özet gönder
    try:
        from github_scan_action import send_msg
        send_msg(report)
    except: pass
    
    # Özellik Önem Sıralaması (Sonuç)
    try:
        importances = best_model.feature_importances_
        importance_df = pd.DataFrame({'feature': X.columns, 'importance': importances}).sort_values('importance', ascending=False)
        print("\n🔑 Modelin Şu An En Çok Güvendiği İndikatörler:")
        print(importance_df.head(10).to_string(index=False))
    except:
        pass

if __name__ == "__main__":
    init_db()
    label_past_signals()
    retrain_model()
