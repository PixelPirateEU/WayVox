Führe im Terminal folgende Befehle aus, um  wtype ,  ydotool , PortAudio, CUDA-Treiber und Hilfswerkzeuge zu installieren:
  
    # 1. Systempakete & Wayland Tools installieren
    sudo pacman -Syu --needed \
        base-devel \           
        python \    
        python-pip \
        portaudio \ 
        wtype \    
        ydotool \
        wl-clipboard \
        cuda \        
        cudnn  
             
    # 2. Eigenen Benutzer zur 'input' Gruppe hinzufügen (für globale evdev Hotkeys)
    sudo usermod -aG input $USER
    
    # 3. ydotoold Daemon aktivieren (optional, falls ydotool genutzt wird)
    sudo systemctl enable --now ydotoold
    
  │ Hinweis zu  input -Rechten: Nach  sudo usermod -aG input $USER  ist einmalig ein Abmelden/Anmelden in CachyOS erforderlich, damit die Rechte wirksam werden.
  
  #### Schritt 2: Python Virtual Environment einrichten & Abhängigkeiten installieren
  
    cd WayVox
             
    # Virtual Environment erstellen
    python3 -m venv venv           
    source venv/bin/activate
    
    # PyTorch mit CUDA 12.x Unterstüzung installieren (optimal für RTX 5070 Ti)
    pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
    
    # Restliche Anforderungen installieren
    pip install -r requirements.txt       
    
  #### Schritt 3: Anwendung starten
  
    ./run.sh
    ──────  
  ### 4. Besonderheiten & Edge-Cases in dieser Implementierung
  
  1. Fokus-Erhalt beim Klick (Wayland / KDE Plasma 6):
      • Das PySide6 Overlay nutzt das Flag  Qt.WindowType.WindowDoesNotAcceptFocus .
      • Dadurch behält die Zielanwendung (z. B. VS Code, Browser, Telegram oder Konsole) beim Klick auf den Kreis ihren Tastaturfokus, sodass die direkte Injektion via  wtype  /  ydotool  reibungslos funktioniert.
  2. Offlinenutzung & Modell-Caching:
      • Das  large-v3  Modell wird beim ersten Start von  faster-whisper  heruntergeladen und lokal unter  ~/.cache/huggingface/hub/  abgelegt. Alle nachfolgenden Aufrufe arbeiten 100 % lokal und offline auf deiner NVIDIA RTX 5070 Ti via Tensor Core CUDA Beschleunigung (FP16).
  3. Performance & Threading:
      • Die Audio-Aufnahme und die CUDA-Transkription sind vollständig entkoppelt in einem separaten  QThread . Das UI bleibt mit 50 FPS butterweich und reagiert sofort auf Benutzereingaben.
