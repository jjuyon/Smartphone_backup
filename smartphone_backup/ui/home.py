"""Écran d'accueil : choix iPhone / Android et état des prérequis."""
from .qt import Qt, Signal
from .qt import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ..core import prereqs
from .common import GREEN, GREY, ORANGE, RED, ClickableCard, label, quit_button, status_html


class HomePage(QWidget):
    chosen = Signal(str)  # "iphone" ou "android"
    help = Signal(str)    # ouvre la fenêtre des prérequis
    quit = Signal()

    def __init__(self):
        super().__init__()
        root = QVBoxLayout(self)
        root.setContentsMargins(40, 18, 40, 30)
        root.setSpacing(10)
        top = QHBoxLayout()
        top.addStretch(1)
        top.addWidget(quit_button(self.quit))
        root.addLayout(top)
        root.addStretch(1)
        t = label("Smartphone Backup", "bigtitle")
        t.setAlignment(Qt.AlignCenter)
        root.addWidget(t)
        s = label("Quel téléphone voulez-vous sauvegarder ?", "subtitle")
        s.setAlignment(Qt.AlignCenter)
        root.addWidget(s)
        root.addSpacing(30)

        row = QHBoxLayout()
        row.setSpacing(24)
        self.st_iphone = self.choice(row, "iphone", "iPhone",
                                     "Sauvegarde complète puis rangement :\nphotos, documents, "
                                     "musique, notes vocales.")
        self.st_android = self.choice(row, "android", "Android",
                                      "Synchronisation incrémentale :\nphotos, musique, documents, "
                                      "WhatsApp, carte SD.")
        root.addLayout(row)
        root.addStretch(2)

        # bandeau des prérequis
        self.banner = QFrame()
        lay = QHBoxLayout(self.banner)
        lay.setContentsMargins(18, 12, 12, 12)
        self.banner_text = QLabel()
        self.banner_text.setWordWrap(True)
        lay.addWidget(self.banner_text, 1)
        self.b_help = QPushButton()
        self.b_help.clicked.connect(lambda: self.help.emit(""))
        lay.addWidget(self.b_help)
        root.addWidget(self.banner)

        self.refresh_prereqs()
        self.update_devices([], [])

    def choice(self, row, key, title, desc):
        c = ClickableCard()
        c.setMinimumSize(280, 220)
        lay = QVBoxLayout(c)
        lay.setContentsMargins(26, 26, 26, 22)
        lay.setSpacing(10)
        lay.addWidget(label(title, "choiceTitle"))
        d = label(desc, "hint")
        d.setWordWrap(True)
        lay.addWidget(d)
        lay.addStretch(1)
        st = QLabel()
        lay.addWidget(st)
        c.clicked.connect(lambda: self.chosen.emit(key))
        row.addWidget(c, 1)
        return st

    def refresh_prereqs(self):
        miss = prereqs.missing()
        required = [p for p in miss if p.required]
        self.missing_targets = {p.target for p in required}
        if required:
            name = "warn"
            text = status_html(ORANGE, "Il manque : " + ", ".join(p.name for p in required))
            self.b_help.setText("Aide à l'installation")
            self.b_help.setObjectName("primary")
        elif miss:
            name = ""
            text = status_html(GREEN, "Prérequis indispensables installés") + \
                f'&nbsp;&nbsp;<span style="color:{GREY}">(recommandé : ' + \
                ", ".join(p.name for p in miss) + ")</span>"
            self.b_help.setText("Voir les prérequis")
            self.b_help.setObjectName("")
        else:
            name = ""
            text = status_html(GREEN, "Tous les prérequis sont installés")
            self.b_help.setText("Voir les prérequis")
            self.b_help.setObjectName("")
        self.banner.setObjectName("bannerWarn" if name else "banner")
        self.banner_text.setText(text)
        for w in (self.banner, self.b_help):  # réapplique le style après changement de nom
            w.style().unpolish(w)
            w.style().polish(w)

    def update_devices(self, iphones, androids):
        self.refresh_prereqs()  # prend en compte une installation faite dans un terminal
        if "iphone" in self.missing_targets:
            self.st_iphone.setText(status_html(RED, "Prérequis manquants"))
        elif iphones:
            self.st_iphone.setText(status_html(GREEN, ", ".join(n for _, n in iphones) + " branché"))
        else:
            self.st_iphone.setText(status_html(GREY, "Aucun iPhone branché"))

        ready = [m for _, state, m in androids if state == "device"]
        if "android" in self.missing_targets:
            self.st_android.setText(status_html(RED, "Prérequis manquants"))
        elif ready:
            self.st_android.setText(status_html(GREEN, ", ".join(ready) + " branché"))
        elif any(state == "no" for _, state, _ in androids):
            self.st_android.setText(status_html(RED, "Accès USB refusé (règles udev)"))
        elif androids:
            self.st_android.setText(status_html(ORANGE, "Débogage USB à autoriser"))
        else:
            self.st_android.setText(status_html(GREY, "Aucun Android branché"))
