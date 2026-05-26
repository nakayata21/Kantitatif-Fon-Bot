import torch
import torch.nn as nn
import torch.optim as optim
import torch.nn.functional as F
from torch.utils.data import DataLoader, TensorDataset
import numpy as np
from typing import Dict, List, Tuple, Optional
import warnings

# ========================================================================= #
# LFM ULTRA ADVANCED DEEP LEARNING ENGINE (PyTorch)
# 
# Gelişmiş Özellikler:
# 1. Graf Tabanlı Öğrenme (GNN): Hisse ilişkilerini modelleme
# 2. Temporal Fusion Transformer (TFT): Gelişmiş zaman serisi dikkati
# 3. Çoklu Görev Öğrenimi: Yön, volatilite ve hacim tahmini
# 4. Belirsizlik Ölçümü: Monte Carlo Dropout ile güven aralığı
# 5. Çevrimiçi Öğrenme: Akış verisine adaptasyon
# 6. Özellik Önemi Analizi: Kararlılık izleme
# 7. Derin Topluluk: Ensemble çeşitliliği
# ========================================================================= #

class GraphStockNetwork(nn.Module):
    """
    Graf Tabanlı Sinir Ağı - Hisse İlişkilerini Modellemek İçin
    Hisseler arası korelasyonları graf yapısı olarak kullanır.
    """
    def __init__(self, input_size, hidden_size=64, num_relations=3):
        super(GraphStockNetwork, self).__init__()
        self.node_embedding = nn.Linear(input_size, hidden_size)
        self.edge_attention = nn.MultiheadAttention(embed_dim=hidden_size, num_heads=4, batch_first=True)
        
        # Graf katmanları
        self.graph_conv1 = nn.Linear(hidden_size * 2, hidden_size)
        self.graph_conv2 = nn.Linear(hidden_size, hidden_size // 2)
        self.relu = nn.ReLU()
        self.dropout = nn.Dropout(0.2)
        
    def forward(self, x, adjacency_matrix=None):
        # x: (batch, seq, features)
        batch_size, seq_len, feat_size = x.shape
        
        # Düğüm yerleştirmeleri
        node_features = self.node_embedding(x.view(-1, feat_size))
        node_features = node_features.view(batch_size * seq_len, -1)
        
        # Basit graf yayılımı (adjacency matrix varsa)
        if adjacency_matrix is not None:
            # Komşu düğümlerden bilgi toplama
            aggregated = torch.matmul(adjacency_matrix, node_features.unsqueeze(0).repeat(batch_size, 1, 1))
            combined = torch.cat([node_features, aggregated.view(-1, node_features.shape[-1])], dim=-1)
            out = self.relu(self.graph_conv1(combined))
            out = self.dropout(out)
            out = self.graph_conv2(out)
        else:
            out = self.relu(self.graph_conv1(torch.cat([node_features, node_features], dim=-1)))
            out = self.graph_conv2(out)
        
        return out.view(batch_size, seq_len, -1)


class TemporalFusionBlock(nn.Module):
    """
    Temporal Fusion Transformer (TFT) Lite Sürümü
    Zaman serilerinde önemli zaman noktalarına odaklanır.
    """
    def __init__(self, input_size, hidden_size=128, num_heads=4):
        super(TemporalFusionBlock, self).__init__()
        
        # Değişken seçim mekanizması
        self.variable_selection = nn.Sequential(
            nn.Linear(input_size, hidden_size),
            nn.GELU(),
            nn.Linear(hidden_size, 1),
            nn.Sigmoid()
        )
        
        # Statik zenginleştirici
        self.static_enrichment = nn.Sequential(
            nn.Linear(input_size, hidden_size),
            nn.LayerNorm(hidden_size),
            nn.GELU(),
            nn.Dropout(0.1)
        )
        
        # Çok başlıklı dikkat
        self.multihead_attn = nn.MultiheadAttention(
            embed_dim=hidden_size,
            num_heads=num_heads,
            batch_first=True,
            dropout=0.1
        )
        
        # Pozisyonel kodlama
        self.positional_encoding = nn.Parameter(torch.randn(1, 100, hidden_size))
        
        # Kapı mekanizması
        self.gate = nn.Sequential(
            nn.Linear(hidden_size, hidden_size),
            nn.Sigmoid()
        )
        
    def forward(self, x, static_context=None):
        # x: (batch, seq, features)
        batch_size, seq_len, _ = x.shape
        
        # Değişken seçimi
        weights = self.variable_selection(x)
        x_weighted = x * weights
        
        # Statik bağlam ekleme
        if static_context is not None:
            static_feat = self.static_enrichment(static_context.unsqueeze(1).expand(-1, seq_len, -1))
            x = x_weighted + static_feat
        else:
            x = x_weighted
        
        # Pozisyonel kodlama
        pos_enc = self.positional_encoding[:, :seq_len, :]
        x = x + pos_enc
        
        # Self-attention
        attn_output, _ = self.multihead_attn(x, x, x)
        
        # Kapı mekanizması + skip connection
        gate = self.gate(attn_output)
        output = gate * attn_output + (1 - gate) * x
        
        return output


class MultiTaskHead(nn.Module):
    """
    Çoklu Görev Çıktı Başlıkları
    Yön, volatilite ve hacim tahmini için ayrı başlıklar.
    """
    def __init__(self, input_size, num_direction_classes=2):
        super(MultiTaskHead, self).__init__()
        
        # Yön tahmini (yükseliş/düşüş)
        self.direction_head = nn.Sequential(
            nn.Linear(input_size, 32),
            nn.GELU(),
            nn.Dropout(0.2),
            nn.Linear(32, num_direction_classes)
        )
        
        # Volatilite tahmini (regresyon)
        self.volatility_head = nn.Sequential(
            nn.Linear(input_size, 32),
            nn.GELU(),
            nn.Dropout(0.2),
            nn.Linear(32, 1)
        )
        
        # Hacim değişimi tahmini (regresyon)
        self.volume_head = nn.Sequential(
            nn.Linear(input_size, 32),
            nn.GELU(),
            nn.Dropout(0.2),
            nn.Linear(32, 1)
        )
        
    def forward(self, x):
        direction_logits = self.direction_head(x)
        volatility_pred = self.volatility_head(x)
        volume_pred = self.volume_head(x)
        
        return direction_logits, volatility_pred, volume_pred


class LSTMCNNAttentionAdvanced(nn.Module):
    """
    Gelişmiş LSTM + CNN + Attention + GNN + TFT Hibrid Modeli
    Tüm gelişmiş özellikleri içerir.
    """
    def __init__(self, input_size, cnn_filters=32, lstm_hidden=128, num_heads=4, 
                 num_direction_classes=2, use_gnn=True, use_tft=True):
        super(LSTMCNNAttentionAdvanced, self).__init__()
        
        self.use_gnn = use_gnn
        self.use_tft = use_tft
        
        # Graf ağı (opsiyonel)
        if self.use_gnn:
            self.graph_network = GraphStockNetwork(input_size, hidden_size=64)
        
        # 1D CNN Katmanları
        self.cnn1 = nn.Conv1d(input_size, cnn_filters, kernel_size=3, padding=1)
        self.bn1 = nn.BatchNorm1d(cnn_filters)
        self.cnn2 = nn.Conv1d(cnn_filters, cnn_filters*2, kernel_size=3, padding=1)
        self.bn2 = nn.BatchNorm1d(cnn_filters*2)
        self.relu = nn.ReLU()
        self.gelu = nn.GELU()
        
        # LSTM Katmanları
        self.lstm1 = nn.LSTM(
            input_size=cnn_filters*2 if not self.use_gnn else 64,
            hidden_size=lstm_hidden,
            num_layers=1,
            batch_first=True,
            dropout=0.2
        )
        
        # Temporal Fusion Block (opsiyonel)
        if self.use_tft:
            self.tft_block = TemporalFusionBlock(lstm_hidden, hidden_size=128, num_heads=num_heads)
        
        # Multi-Head Attention
        self.attention = nn.MultiheadAttention(
            embed_dim=lstm_hidden,
            num_heads=num_heads,
            batch_first=True,
            dropout=0.2
        )
        
        # İkinci LSTM
        self.lstm2 = nn.LSTM(
            input_size=lstm_hidden,
            hidden_size=64,
            num_layers=1,
            batch_first=True
        )
        
        # Çoklu görev başlıkları
        self.multi_task_head = MultiTaskHead(64, num_direction_classes)
        
        # Monte Carlo Dropout için ek dropout
        self.mc_dropout = nn.Dropout(0.3)
        
    def forward(self, x, adjacency_matrix=None, static_context=None, return_intermediate=False):
        # x shape: (batch_size, sequence_length, features)
        batch_size = x.shape[0]
        
        # Graf ağı (varsa)
        if self.use_gnn:
            x_graph = self.graph_network(x, adjacency_matrix)
        
        # CNN için şekli değiştir: (batch, features, sequence)
        x_cnn = x.transpose(1, 2)
        
        # CNN katmanları
        x_cnn = self.relu(self.bn1(self.cnn1(x_cnn)))
        x_cnn = self.relu(self.bn2(self.cnn2(x_cnn)))
        
        # LSTM için şekli geri çevir: (batch, sequence, channels)
        x_cnn = x_cnn.transpose(1, 2)
        
        # Graf ve CNN çıktılarını birleştir
        if self.use_gnn:
            x = torch.cat([x_graph, x_cnn], dim=-1)
            x = self.gelu(nn.Linear(x.shape[-1], self.lstm1.input_size)(x))
        else:
            x = x_cnn
        
        # LSTM 1
        x, (h1, c1) = self.lstm1(x)
        
        # TFT Block (varsa)
        if self.use_tft:
            x = self.tft_block(x, static_context)
        
        # Attention
        x, _ = self.attention(x, x, x)
        
        # LSTM 2
        x, (h2, c2) = self.lstm2(x)
        
        # Son zaman birimini (t) al
        x_final = x[:, -1, :]
        
        # Çoklu görev çıktıları
        direction_logits, volatility_pred, volume_pred = self.multi_task_head(x_final)
        
        if return_intermediate:
            return direction_logits, volatility_pred, volume_pred, x_final
        else:
            return direction_logits, volatility_pred, volume_pred


class MonteCarloDropout:
    """
    Belirsizlik Ölçümü için Monte Carlo Dropout
    Tahmin sırasında dropout'u aktif tutarak çoklu örneklem alır.
    """
    def __init__(self, model, num_samples=50):
        self.model = model
        self.num_samples = num_samples
        
    def predict_with_uncertainty(self, X, adjacency_matrix=None, static_context=None):
        """
        Çoklu ön geçişlerle tahmin ve belirsizlik hesaplama.
        """
        self.model.train()  # Dropout'u aktif etmek için train modunda
        
        direction_probs_list = []
        volatility_preds = []
        volume_preds = []
        
        with torch.no_grad():
            for _ in range(self.num_samples):
                dir_logits, vol_pred, volu_pred = self.model(X, adjacency_matrix, static_context)
                dir_probs = F.softmax(dir_logits, dim=1)
                
                direction_probs_list.append(dir_probs.cpu().numpy())
                volatility_preds.append(vol_pred.cpu().numpy())
                volume_preds.append(volu_pred.cpu().numpy())
        
        self.model.eval()
        
        # Ortalama ve standart sapma hesaplama
        direction_probs_mean = np.mean(direction_probs_list, axis=0)
        direction_probs_std = np.std(direction_probs_list, axis=0)
        
        volatility_mean = np.mean(volatility_preds, axis=0)
        volatility_std = np.std(volatility_preds, axis=0)
        
        volume_mean = np.mean(volume_preds, axis=0)
        volume_std = np.std(volume_preds, axis=0)
        
        return {
            'direction': {
                'mean': direction_probs_mean,
                'std': direction_probs_std,  # Belirsizlik ölçüsü
                'prediction': np.argmax(direction_probs_mean, axis=1)
            },
            'volatility': {
                'mean': volatility_mean,
                'std': volatility_std
            },
            'volume': {
                'mean': volume_mean,
                'std': volume_std
            }
        }


class FeatureImportanceTracker:
    """
    Özellik Önemi Kararlılığını İzleme
    Hangi özelliklerin tahminde daha etkili olduğunu ve zamanla değişimini takip eder.
    """
    def __init__(self, feature_names):
        self.feature_names = feature_names
        self.importance_history = []
        self.baseline_importance = None
        
    def compute_permutation_importance(self, model, X, y, n_repeats=10):
        """
        Permütasyon tabanlı özellik önemi hesaplama.
        X: Zaten sequence formatında olmalı (N, seq, features)
        """
        # is_sequence=True ile çağır çünkü X zaten sequence formatında
        base_probs = model.predict_proba(X, adjacency_matrix=None, static_context=None, is_sequence=True)
        base_score = np.mean(np.argmax(base_probs, axis=1) == y)
        
        importance_scores = []
        
        for feat_idx in range(X.shape[2]):  # Features üzerinden iterasyon
            scores = []
            for _ in range(n_repeats):
                X_permuted = X.copy()
                # Özelliği karıştır
                X_permuted[:, :, feat_idx] = np.random.permutation(X_permuted[:, :, feat_idx])
                
                perm_probs = model.predict_proba(X_permuted, adjacency_matrix=None, static_context=None, is_sequence=True)
                perm_score = np.mean(np.argmax(perm_probs, axis=1) == y)
                
                scores.append(base_score - perm_score)
            
            importance_scores.append(np.mean(scores))
        
        return np.array(importance_scores)
    
    def track_importance(self, importance_scores):
        """Önem skorlarını kaydet ve kararlılığı kontrol et."""
        self.importance_history.append(importance_scores)
        
        if len(self.importance_history) > 1:
            # Önceki önemlerle karşılaştır
            prev_importance = np.mean(self.importance_history[:-1], axis=0)
            drift = np.abs(importance_scores - prev_importance)
            
            # Yüksek sapma tespit et
            unstable_features = np.where(drift > 0.1)[0]
            
            return {
                'current': importance_scores,
                'drift': drift,
                'unstable_features': unstable_features,
                'feature_names': [self.feature_names[i] if i < len(self.feature_names) else f'feat_{i}' 
                                 for i in unstable_features]
            }
        
        return {'current': importance_scores}


class LFMPyTorchTrainerAdvanced:
    """
    Gelişmiş Scikit-Learn Uyumlu PyTorch Eğitmeni
    Tüm gelişmiş özellikleri destekler.
    """
    def __init__(self, input_dim, feature_names=None, epochs=40, lr=0.001, batch_size=64, 
                 seq_length=10, use_gnn=True, use_tft=True, enable_uncertainty=True):
        self.input_dim = input_dim
        self.feature_names = feature_names or [f'feat_{i}' for i in range(input_dim)]
        self.epochs = epochs
        self.lr = lr
        self.batch_size = batch_size
        self.seq_length = seq_length
        self.use_gnn = use_gnn
        self.use_tft = use_tft
        self.enable_uncertainty = enable_uncertainty
        
        self.device = torch.device('cuda' if torch.cuda.is_available() else 
                                  'mps' if torch.backends.mps.is_available() else 'cpu')
        
        print(f"🚀 LFM Ultra Advanced Engine Çalışıyor! Cihaz: {self.device}")
        print(f"   ├─ GNN: {'Aktif' if use_gnn else 'Pasif'}")
        print(f"   ├─ TFT: {'Aktif' if use_tft else 'Pasif'}")
        print(f"   ├─ Çoklu Görev: Yön + Volatilite + Hacim")
        print(f"   └─ Belirsizlik: {'Aktif' if enable_uncertainty else 'Pasif'}")
        
        # Model
        self.model = LSTMCNNAttentionAdvanced(
            input_size=input_dim,
            cnn_filters=32,
            lstm_hidden=128,
            num_heads=4,
            use_gnn=use_gnn,
            use_tft=use_tft
        ).to(self.device)
        
        # Çoklu görev kayıp fonksiyonları
        self.direction_criterion = nn.CrossEntropyLoss(label_smoothing=0.1)
        self.volatility_criterion = nn.MSELoss()
        self.volume_criterion = nn.MSELoss()
        
        # Optimizer
        self.optimizer = optim.AdamW(self.model.parameters(), lr=self.lr, weight_decay=1e-4)
        self.scheduler = optim.lr_scheduler.ReduceLROnPlateau(self.optimizer, mode='min', factor=0.5, patience=5)
        
        # Yardımcı sınıflar
        self.mc_dropout = MonteCarloDropout(self.model) if enable_uncertainty else None
        self.feature_tracker = FeatureImportanceTracker(self.feature_names)
        
        # Çevrimiçi öğrenme için
        self.online_learning_rate = lr * 0.1
        self._is_pretrained = False
        self.training_history = []
        
    def _create_sequences(self, X):
        """2D veriyi 3D sequence formatına çevir."""
        N, F = X.shape
        out = np.zeros((N, self.seq_length, F), dtype=np.float32)
        
        for i in range(N):
            start_idx = i - self.seq_length + 1
            if start_idx < 0:
                pad_size = abs(start_idx)
                pad_block = np.repeat([X[0]], pad_size, axis=0)
                real_block = X[0: i+1]
                seq = np.vstack([pad_block, real_block])
            else:
                seq = X[start_idx: i+1]
            out[i] = seq
        
        return out
    
    def _compute_multi_task_loss(self, direction_logits, volatility_pred, volume_pred, 
                                  y_direction, y_volatility, y_volume, alpha=0.6, beta=0.2, gamma=0.2):
        """Çoklu görev kaybını hesapla."""
        loss_direction = self.direction_criterion(direction_logits, y_direction)
        loss_volatility = self.volatility_criterion(volatility_pred.squeeze(), y_volatility)
        loss_volume = self.volume_criterion(volume_pred.squeeze(), y_volume)
        
        total_loss = alpha * loss_direction + beta * loss_volatility + gamma * loss_volume
        return total_loss, loss_direction, loss_volatility, loss_volume
    
    def fit(self, X, y_direction, y_volatility=None, y_volume=None, 
            adjacency_matrix=None, static_context=None, validation_data=None):
        """
        Modeli çoklu görevlerle eğit.
        
        Parametreler:
        - X: Özellik matrisi (samples, features)
        - y_direction: Yön etiketleri (0/1)
        - y_volatility: Volatilite değerleri (opsiyonel)
        - y_volume: Hacim değişimi (opsiyonel)
        - adjacency_matrix: Graf komşuluk matrisi (opsiyonel)
        - static_context: Statik bağlam özellikleri (opsiyonel)
        """
        if hasattr(X, "values"): X = X.values
        if hasattr(y_direction, "values"): y_direction = y_direction.values
        
        # Varsayılan değerler
        if y_volatility is None:
            y_volatility = np.zeros(len(y_direction))
        if y_volume is None:
            y_volume = np.zeros(len(y_direction))
        
        # Sequence oluştur
        X_seq = self._create_sequences(X)
        
        # Tensörlere çevir
        X_t = torch.FloatTensor(X_seq).to(self.device)
        y_dir_t = torch.LongTensor(y_direction).to(self.device)
        y_vol_t = torch.FloatTensor(y_volatility).to(self.device)
        y_volu_t = torch.FloatTensor(y_volume).to(self.device)
        
        # Adjacency matrix
        adj_t = torch.FloatTensor(adjacency_matrix).to(self.device) if adjacency_matrix is not None else None
        
        # Statik bağlam
        static_t = torch.FloatTensor(static_context).to(self.device) if static_context is not None else None
        
        dataset = TensorDataset(X_t, y_dir_t, y_vol_t, y_volu_t)
        loader = DataLoader(dataset, batch_size=self.batch_size, shuffle=True)
        
        self.model.train()
        best_loss = float('inf')
        
        for ep in range(self.epochs):
            total_loss = 0
            total_dir_loss = 0
            total_vol_loss = 0
            total_volatility_loss = 0
            
            for batch_X, batch_y_dir, batch_y_vol, batch_y_volatility in loader:
                self.optimizer.zero_grad()
                
                # İleri geçiş
                dir_logits, vol_pred, volu_pred = self.model(
                    batch_X, adjacency_matrix=adj_t, static_context=static_t
                )
                
                # Çoklu görev kaybı
                loss, dir_loss, vol_loss, volatility_loss = self._compute_multi_task_loss(
                    dir_logits, vol_pred, volu_pred,
                    batch_y_dir, batch_y_vol, batch_y_volatility
                )
                
                loss.backward()
                torch.nn.utils.clip_grad_norm_(self.model.parameters(), max_norm=1.0)
                self.optimizer.step()
                
                total_loss += loss.item()
                total_dir_loss += dir_loss.item()
                total_vol_loss += vol_loss.item()
                total_volatility_loss += volatility_loss.item()
            
            avg_loss = total_loss / len(loader)
            avg_dir_loss = total_dir_loss / len(loader)
            avg_vol_loss = total_vol_loss / len(loader)
            avg_volatility_loss = total_volatility_loss / len(loader)
            
            self.scheduler.step(avg_loss)
            self.training_history.append({
                'epoch': ep + 1,
                'total_loss': avg_loss,
                'direction_loss': avg_dir_loss,
                'volatility_loss': avg_vol_loss,
                'volume_loss': avg_volatility_loss,
                'lr': self.optimizer.param_groups[0]['lr']
            })
            
            # En iyi modeli kaydet
            if avg_loss < best_loss:
                best_loss = avg_loss
            
            if (ep + 1) % 10 == 0 or ep == 0:
                print(f"   🌀 Epoch [{ep+1}/{self.epochs}] - "
                      f"Toplam Kayıp: {avg_loss:.4f} (Yön: {avg_dir_loss:.3f}, "
                      f"Volatilite: {avg_vol_loss:.3f}, Hacim: {avg_volatility_loss:.3f}) - "
                      f"LR: {self.optimizer.param_groups[0]['lr']:.6f}")
        
        self._is_pretrained = True
        
        # Özellik önemini hesapla
        if len(self.training_history) > 0:
            self._compute_feature_importance(X_seq, y_direction)
        
        return self
    
    def partial_fit(self, X, y_direction, y_volatility=None, y_volume=None, 
                   n_epochs=5, adjacency_matrix=None, static_context=None):
        """
        Çevrimiçi öğrenme: Yeni veriyle modeli hızlıca güncelle.
        """
        if not self._is_pretrained:
            warnings.warn("Model henüz tam eğitimden geçirilmedi. partial_fit yerine fit kullanın.")
            return self.fit(X, y_direction, y_volatility, y_volume, adjacency_matrix, static_context)
        
        # Öğrenme oranını düşür
        old_lr = self.optimizer.param_groups[0]['lr']
        for param_group in self.optimizer.param_groups:
            param_group['lr'] = self.online_learning_rate
        
        # Kısa eğitim
        self.fit(X, y_direction, y_volatility, y_volume, adjacency_matrix, static_context, 
                validation_data=None)
        
        # Öğrenme oranını geri yükle
        for param_group in self.optimizer.param_groups:
            param_group['lr'] = old_lr
        
        return self
    
    def _compute_feature_importance(self, X_seq, y_direction):
        """Özellik önemini hesapla ve izle."""
        if self.feature_tracker.baseline_importance is None:
            # X_seq zaten sequence formatında (N, seq, features)
            importance = self.feature_tracker.compute_permutation_importance(
                self, X_seq, y_direction, n_repeats=3
            )
            result = self.feature_tracker.track_importance(importance)
            self.feature_tracker.baseline_importance = importance
            
            # Önemli özellikleri yazdır
            top_indices = np.argsort(importance)[-10:][::-1]
            print("\n   📊 En Önemli 10 Özellik:")
            for idx in top_indices:
                feat_name = self.feature_names[idx] if idx < len(self.feature_names) else f'feat_{idx}'
                print(f"      {feat_name}: {importance[idx]:.4f}")
    
    def predict_proba(self, X, adjacency_matrix=None, static_context=None, is_sequence=False):
        """Yön tahmini olasılıkları."""
        self.model.eval()
        if hasattr(X, "values"): X = X.values
        
        # Eğer veri zaten sequence formatındaysa dönüştürme
        if is_sequence:
            X_seq = X
        else:
            X_seq = self._create_sequences(X)
        
        X_t = torch.FloatTensor(X_seq).to(self.device)
        
        adj_t = torch.FloatTensor(adjacency_matrix).to(self.device) if adjacency_matrix is not None else None
        static_t = torch.FloatTensor(static_context).to(self.device) if static_context is not None else None
        
        with torch.no_grad():
            dir_logits, _, _ = self.model(X_t, adjacency_matrix=adj_t, static_context=static_t)
            probs = F.softmax(dir_logits, dim=1)
        
        return probs.cpu().numpy()
    
    def predict(self, X, adjacency_matrix=None, static_context=None):
        """Yön tahmini (0 veya 1)."""
        probs = self.predict_proba(X, adjacency_matrix, static_context)
        return np.argmax(probs, axis=1)
    
    def predict_with_uncertainty(self, X, adjacency_matrix=None, static_context=None, num_samples=50):
        """
        Belirsizlik ölçümüyle birlikte tahmin.
        """
        if not self.enable_uncertainty:
            raise ValueError("Belirsizlik özelliği aktif değil. enable_uncertainty=True ile başlatın.")
        
        if hasattr(X, "values"): X = X.values
        X_seq = self._create_sequences(X)
        X_t = torch.FloatTensor(X_seq).to(self.device)
        
        adj_t = torch.FloatTensor(adjacency_matrix).to(self.device) if adjacency_matrix is not None else None
        static_t = torch.FloatTensor(static_context).to(self.device) if static_context is not None else None
        
        return self.mc_dropout.predict_with_uncertainty(X_t, adj_t, static_t)
    
    def get_feature_importance(self, X, y, n_repeats=10):
        """Özellik önem skorlarını döndür."""
        if hasattr(X, "values"): X = X.values
        X_seq = self._create_sequences(X)
        
        importance = self.feature_tracker.compute_permutation_importance(self, X_seq, y, n_repeats)
        result = self.feature_tracker.track_importance(importance)
        
        return {
            'importance': importance,
            'feature_names': self.feature_names,
            'ranking': np.argsort(importance)[::-1],
            'stability_analysis': result
        }
    
    def get_params(self, deep=True):
        return {
            'input_dim': self.input_dim,
            'epochs': self.epochs,
            'lr': self.lr,
            'batch_size': self.batch_size,
            'seq_length': self.seq_length,
            'use_gnn': self.use_gnn,
            'use_tft': self.use_tft,
            'enable_uncertainty': self.enable_uncertainty
        }
    
    def set_params(self, **params):
        for k, v in params.items():
            setattr(self, k, v)
        return self
    
    def save_model(self, path):
        """Modeli kaydet."""
        torch.save({
            'model_state_dict': self.model.state_dict(),
            'optimizer_state_dict': self.optimizer.state_dict(),
            'training_history': self.training_history,
            'config': self.get_params()
        }, path)
        print(f"💾 Model kaydedildi: {path}")
    
    def load_model(self, path):
        """Modeli yükle."""
        checkpoint = torch.load(path, map_location=self.device)
        self.model.load_state_dict(checkpoint['model_state_dict'])
        self.optimizer.load_state_dict(checkpoint['optimizer_state_dict'])
        self.training_history = checkpoint.get('training_history', [])
        
        config = checkpoint.get('config', {})
        for k, v in config.items():
            if hasattr(self, k):
                setattr(self, k, v)
        
        print(f"📂 Model yüklendi: {path}")
        return self
