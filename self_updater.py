
import os
import sys
import subprocess
import time
import logging
import threading

# AI Trader logger'ına bağla
logger = logging.getLogger('ai_trader.updater')

class AutoUpdater:
    """
    Git tabanlı otomatik güncelleme mekanizması.
    Sistemi github üzerinden kontrol eder, değişiklik varsa çeker ve process'i restart eder.
    """
    def __init__(self, interval=3600):
        self.interval = interval # Kontrol aralığı (saniye)
        self.repo_path = os.getcwd()
        self.is_running = False

    def check_for_updates(self):
        """Uzak depoyu kontrol eder ve gerekirse sistemi günceller."""
        logger.info("🔄 [UPDATER] Uzak depo güncellemeleri kontrol ediliyor...")
        try:
            # 1. Fetch: Değişiklikleri sadece kontrol et, birleştirme yapma
            subprocess.run(["git", "fetch"], cwd=self.repo_path, capture_output=True, check=True)
            
            # 2. Status: Yerel branch ile uzak branch farkını kontrol et
            status = subprocess.check_output(["git", "status", "-uno"], cwd=self.repo_path).decode("utf-8")
            
            if "Your branch is behind" in status:
                logger.warning("🚀 [UPDATER] Yeni kod sürümü tespit edildi! Güncelleme başlatılıyor...")
                
                # Güncelleme öncesi son commit mesajını al (Değişiklikleri görmek için)
                commit_msg = subprocess.check_output(
                    ["git", "log", "HEAD..origin/main", "--oneline"], cwd=self.repo_path
                ).decode("utf-8").strip()
                
                # 3. Pull: Değişiklikleri çek
                subprocess.run(["git", "stash"], cwd=self.repo_path)
                subprocess.run(["git", "pull"], cwd=self.repo_path, check=True)
                subprocess.run(["git", "stash", "pop"], cwd=self.repo_path)
                
                # 4. Dependency: Gereksinimleri güncelle
                if os.path.exists("requirements.txt"):
                    subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"], check=True)
                
                # 5. Telegram Bildirimi: Kullanıcıya değişikliği haber ver
                self.notify_user(commit_msg)
                
                # 6. Hot Reload: Restart
                logger.error("🔄 [UPDATER] Sisteme yeni güncellemeler uygulandı. BOT YENİDEN BAŞLATILIYOR...")
                time.sleep(2) # Mesajın gitmesi için bekle
                os.execv(sys.executable, [sys.executable] + sys.argv)
            else:
                logger.info("✅ [UPDATER] Sistem şu an en güncel sürümde.")
                
        except Exception as e:
            logger.error(f"❌ [UPDATER] Güncelleme sırasında kritik hata: {e}")

    def notify_user(self, commit_msg):
        """Telegram üzerinden güncelleme bilgisini gönderir."""
        try:
            from utils import send_telegram_message
            token = os.environ.get("TELEGRAM_BOT_TOKEN")
            chat_id = os.environ.get("TELEGRAM_CHAT_ID")
            
            msg = f"🚀 **OTONOM GÜNCELLEME TAMAMLANDI**\n\n📌 **Değişiklikler:**\n`{commit_msg[:500]}`\n\n🔄 Bot yeni kodlarla tekrar başlatılıyor..."
            send_telegram_message(token, chat_id, msg)
        except:
            pass

    def _loop(self):
        """Arka plan döngüsü."""
        while self.is_running:
            self.check_for_updates()
            time.sleep(self.interval)

    def start_background(self):
        """Güncelleyiciyi ayrı bir kanalda başlatır."""
        if not self.is_running:
            self.is_running = True
            thread = threading.Thread(target=self._loop, daemon=True)
            thread.start()
            logger.info(f"🛰️ [UPDATER] Otonom Güncelleyici Aktif (Aralık: {self.interval}s)")

def start_autoupdater(interval=3600):
    updater = AutoUpdater(interval=interval)
    updater.start_background()
    return updater

if __name__ == "__main__":
    # Manuel test için
    logging.basicConfig(level=logging.INFO)
    updater = AutoUpdater(interval=10)
    updater.check_for_updates()
