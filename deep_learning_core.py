import torch
import torch.nn as nn
import torch.optim as optim
import torch.nn.functional as F
from torch.utils.data import DataLoader, TensorDataset
import numpy as np

# ========================================================================= #
# LFM ULTRA DEEP LEARNING ENGINE (PyTorch)
# 
# Mimari: LSTM + 1D-CNN + Multi-Head Attention Hibrid
# Özellikler:
# 1. CNN: Yerel fiyat/hacim desenlerini (bayrak, flama vb.) yakalar.
# 2. LSTM: Uzun dönemli fiyat belleklerini ve geçmiş dirençleri hafızada tutar.
# 3. Attention: En önemli "zaman dilimine" odaklanarak gürültüyü eler.
# ========================================================================= #

class LSTMCNNAttention(nn.Module):
    """
    LSTM + CNN + Attention Hibrid Modeli
    Boyut beklentisi: (Batch, Sequence, Features)
    """
    def __init__(self, input_size, cnn_filters=32, lstm_hidden=128, num_heads=4, num_classes=2):
        super(LSTMCNNAttention, self).__init__()
        
        # 1D CNN Katmanları - Sequence üzerinden değil Feature üzerinden yerel ilişki de aranabilir 
        # ama klasik kullanımda Convolution zaman (sequence) üzerinde gezer.
        # Conv1d girdi boyutu: (Batch, Channels/Features, Sequence)
        self.cnn1 = nn.Conv1d(input_size, cnn_filters, kernel_size=3, padding=1)
        self.cnn2 = nn.Conv1d(cnn_filters, cnn_filters*2, kernel_size=3, padding=1)
        self.relu = nn.ReLU()
        # Eğer sequence boyutu küçükse (örn 10), maxpool boyutu ufaltır, kernel'a dikkat etmeliyiz
        # Güvenlik için padding ekliyoruz
        
        # LSTM Katmanları
        self.lstm1 = nn.LSTM(
            input_size=cnn_filters*2,
            hidden_size=lstm_hidden,
            num_layers=1,
            batch_first=True,
            dropout=0.2
        )
        
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
        
        # Karar Katmanları
        self.fc1 = nn.Linear(64, 32)
        self.fc2 = nn.Linear(32, 16)
        # Sınıflandırıcı (CrossEntropy kullanıldığından numarası sınıf sayısıdır, boyut: 2)
        self.classifier = nn.Linear(16, num_classes)
        self.dropout = nn.Dropout(0.3)

    def forward(self, x):
        # x shape: (batch_size, sequence_length, features)
        
        # CNN için şekli değiştir: (batch, features, sequence)
        x = x.transpose(1, 2)
        
        # CNN katmanları
        x = self.relu(self.cnn1(x))
        x = self.relu(self.cnn2(x))
        # Sequence uzunluğunu çok kısaltmamak için pooling'i opsiyonel tutuyoruz veya atlıyoruz
        
        # LSTM için şekli geri çevir: (batch, sequence, channels)
        x = x.transpose(1, 2)
        
        # LSTM 1
        x, (h1, c1) = self.lstm1(x)
        
        # Attention
        x, _ = self.attention(x, x, x)
        
        # LSTM 2
        x, (h2, c2) = self.lstm2(x)
        
        # Son zaman birimini (t) al
        x = x[:, -1, :]
        
        # Dense katmanlar
        x = self.dropout(self.relu(self.fc1(x)))
        x = self.dropout(self.relu(self.fc2(x)))
        logits = self.classifier(x)
        
        return logits


class LFMPyTorchTrainer:
    """
    Scikit-Learn uyumlu LSTM Ağlayıcısı. Tablo (satır) verisini alır,
    otomatik olarak zaman serisi (Sequence) matrisine dönüştürüp LSTM'e besler.
    """
    def __init__(self, input_dim, epochs=40, lr=0.001, batch_size=64, seq_length=10):
        self.input_dim = input_dim
        self.epochs = epochs
        self.lr = lr
        self.batch_size = batch_size
        self.seq_length = seq_length  # LSTM İçin geriye dönük bakılacak bar sayısı
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'mps' if torch.backends.mps.is_available() else 'cpu')
        
        print(f"🤖 PyTorch LSTM+CNN Motoru Çalışıyor! Cihaz: {self.device} (Pencere: {seq_length})")
        
        # num_heads = input_dim veya belirlenen hidden boyutunu tam bölmelidir.
        # lstm_hidden 128 olduğundan num_heads 4 (128 % 4 == 0) güvenlidir.
        self.model = LSTMCNNAttention(input_size=input_dim, cnn_filters=32, lstm_hidden=128, num_heads=4).to(self.device)
        self.criterion = nn.CrossEntropyLoss(label_smoothing=0.1) 
        self.optimizer = optim.AdamW(self.model.parameters(), lr=self.lr, weight_decay=1e-4)
        self.scheduler = optim.lr_scheduler.ReduceLROnPlateau(self.optimizer, mode='min', factor=0.5, patience=5)
        self._is_pretrained = False

    def _create_sequences(self, X):
        """
        Gelen 2D Scikit tablo verisini (Örn: 1000, Features), LSTM'in beklediği 
        3D formata çevirir (1000, Seq, Features). Eksik başları kopyalarak (padding) doldurur.
        """
        N, F = X.shape
        out = np.zeros((N, self.seq_length, F), dtype=np.float32)
        for i in range(N):
            start_idx = i - self.seq_length + 1
            if start_idx < 0:
                # Yetmeyen kısmı satır 0 ile tekrarla (padding)
                pad_size = abs(start_idx)
                pad_block = np.repeat([X[0]], pad_size, axis=0)
                real_block = X[0: i+1]
                seq = np.vstack([pad_block, real_block])
            else:
                seq = X[start_idx: i+1]
                
            out[i] = seq
        return out

    def pre_train_self_supervised(self, X_unlabeled):
        """
        Devre İçi Bırakıldı: LSTM Sequence pre-training mimarisi farklı olduğundan 
        hızlı adaptasyon için şimdilik atlanıyor.
        """
        self._is_pretrained = True
        pass

    def fit(self, X, y):
        if hasattr(X, "values"): X = X.values
        if hasattr(y, "values"): y = y.values
        
        # Veriyi Sequence Formatına (Batch, Seq, Features) çevir
        X_seq = self._create_sequences(X)
        
        X_t = torch.FloatTensor(X_seq).to(self.device)
        y_t = torch.LongTensor(y).to(self.device)
        
        dataset = TensorDataset(X_t, y_t)
        loader = DataLoader(dataset, batch_size=self.batch_size, shuffle=True)
        
        self.model.train()
        
        for ep in range(self.epochs):
            total_loss = 0
            for batch_X, batch_y in loader:
                self.optimizer.zero_grad()
                
                logits = self.model(batch_X)
                loss = self.criterion(logits, batch_y)
                
                loss.backward()
                torch.nn.utils.clip_grad_norm_(self.model.parameters(), max_norm=1.0)
                self.optimizer.step()
                
                total_loss += loss.item()
            
            avg_loss = total_loss / len(loader)
            self.scheduler.step(avg_loss)
            
            if (ep + 1) % 10 == 0 or ep == 0:
                print(f"   🌀 LSTM+CNN Epoch [{ep+1}/{self.epochs}] - Loss: {avg_loss:.4f} - LR: {self.optimizer.param_groups[0]['lr']:.6f}")
                
        return self

    def predict_proba(self, X):
        self.model.eval()
        if hasattr(X, "values"): X = X.values
        
        # Sequence Çevirisi
        X_seq = self._create_sequences(X)
        X_t = torch.FloatTensor(X_seq).to(self.device)
        
        with torch.no_grad():
            logits = self.model(X_t)
            probs = F.softmax(logits, dim=1)
            
        return probs.cpu().numpy()

    def predict(self, X):
        probs = self.predict_proba(X)
        return np.argmax(probs, axis=1)
    
    # Model kaydetme ve entegrasyon metodları için gereksinim
    def get_params(self, deep=True):
        return {
            'input_dim': self.input_dim,
            'epochs': self.epochs,
            'lr': self.lr,
            'batch_size': self.batch_size
        }
    
    def set_params(self, **params):
        for k, v in params.items():
            setattr(self, k, v)
        return self
