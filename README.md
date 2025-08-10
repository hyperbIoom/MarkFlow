# MarkFlow

*Just a simple note-taking app...*

![MarkFlow Screenshot](https://i.ibb.co/qFDZvY9g/Screenshot-From-2025-08-10-20-14-57.png) <!-- Optional: Add a real screenshot later -->

## 🌟 What is MarkFlow?

MarkFlow is a **modern, distraction-free markdown editor** with a clean GNOME-style interface.
It’s built with **Python (Flask + PyWebView)** on the backend and **Toast UI Editor** on the frontend, giving you a powerful yet simple way to write, edit, and manage your markdown documents.

Whether you’re drafting notes, writing docs, or crafting the next big idea — MarkFlow keeps you in the zone.

---

## ✨ Features

* **GNOME-inspired UI** – Smooth light/dark theme that follows your system.
* **Multi-tab editing** – Open multiple notes in separate tabs.
* **Live preview** – See your markdown rendered instantly.
* **Auto-save** – Never lose your work (configurable interval).
* **Export options** – Save as Markdown, HTML, PDF, or plain text.
* **File queue support** – Open `.md` files instantly from command line or OS integration.
* **Cross-platform** – Works on Linux, macOS, and Windows.

---

## 🚀 Quick Start

### 1. Clone the repo

```bash
git clone https://github.com/hyperbIoom/MarkFlow
cd MarkFlow
```

### 2. Install dependencies

Make sure you have **Python 3.8+** installed.

```bash
pip install -r requirements.txt
```

### 3. Run MarkFlow

```bash
python app.py
```

This will start the backend server and open MarkFlow in a desktop window.

---

## 🛠 Configuration

MarkFlow reads settings from `config.yaml` (optional).
You can customize:

* Theme (`light`, `dark`, or `system`)
* Auto-save interval
* Editor toolbar layout
  Example:

```yaml
theme: system
autoSave: true
autoSaveInterval: 30000
```

---

## 🎯 Usage Tips

* **Open a file directly:**

  ```bash
  python app.py mynote.md
  ```

  This will open `mynote.md` in a new tab instantly.
* **Drag-and-drop support** *(coming soon)* for quick file opening.
* **Tabs** let you keep multiple documents open at once.

---

## 📦 Tech Stack

* **Backend:** Python, Flask, PyWebView, FileLock
* **Frontend:** HTML, CSS, JavaScript, Toast UI Editor
* **Styling:** GNOME-style theming with light/dark mode

---

## 🤝 Contributing

Pull requests are welcome!
If you’d like to add a feature or fix a bug:

1. Fork the repo
2. Create a feature branch
3. Submit a PR

---

## 📄 License

This project is licensed under the [GNU GPL-3.0](LICENSE).
Feel free to use, modify, and share.

---

**MarkFlow** – *Capture ideas. Build them into reality.*

