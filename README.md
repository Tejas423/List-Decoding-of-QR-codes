# List Decoding of QR Codes

Welcome to the **List Decoding of QR Codes** interactive web application!

🌐 **Live Demo:** [https://list-decoding-of-qr-codes.streamlit.app/](https://list-decoding-of-qr-codes.streamlit.app/)

This application was developed as part of a Master's Thesis Project (MTP) at the CSE Department, IIT Bombay. It is a powerful, educational visualization tool built with Streamlit that allows you to explore the inner workings of QR codes, understand their physical layout, and most importantly, experiment with **Wu's List Decoding Algorithm**.

Unlike standard decoders found on smartphones (which use the Berlekamp-Massey algorithm), this application demonstrates how list decoding can mathematically recover data from QR codes that have sustained damage **beyond the unique decoding radius**.

---

## ✨ Features

The application is divided into four main interactive tabs:

### 🎛️ Tab 1: Generate & Corrupt (Interactive Playground)
- **Dynamic Encoding:** Type any text, select a QR Code Version (1–40), and choose an Error Correction Level (Low, Medium, Quartile, High). The app instantly generates a valid QR code on the fly.
- **Anatomy & Block Layout Explorer:** View exactly where the Finder, Alignment, Timing, Format, and Version patterns are located. The blocks are color-coded, distinguishing between your actual data and the error correction parity bytes.
- **Capacity Meter:** A visual meter shows exactly how many errors your QR code can sustain before the standard BM algorithm fails, and how many *additional* errors Wu's algorithm can recover.
- **Interactive Damage Injection:** Use an interactive slider to inject physical errors into the QR code. Watch in real-time as the standard Berlekamp-Massey (BM) decoder fails, while **Wu's List Decoder** successfully recovers the original message utilizing its extended mathematical radius!

### 📤 Tab 2: Upload & Decode
- **Test Real Images:** Upload your own severely damaged or scratched QR code images directly into the app.
- **Real-world Recovery:** The app will process your image, extract the underlying binary matrix, and attempt to decode it using both the standard BM algorithm and Wu's List Decoding algorithm side-by-side, proving the algorithm's superiority on real-world damaged data.

### 📷 Tab 3: Live Scanner
- **Webcam Integration:** Use your device's webcam to scan physical QR codes in real-time.
- **Instant Decoding:** Point your camera at a QR code, and the app will instantly extract the matrix and run it through the decoding pipeline, showing you the exact Reed-Solomon boundaries and recovery status.

### 🔀 Tab 4: Ambiguous Channel
- **Why "List" Decoding?** In most normal cases, Wu's algorithm returns exactly one recovered message. This tab demonstrates the true mathematical nature of *List* decoding!
- **Overlapping Spheres Visualization:** It crafts a highly specific "ambiguous" received word that sits mathematically equidistant inside the decoding spheres of *two different valid codewords*.
- **Multiple Candidates:** Because the corrupted message is equally close to two valid messages, Wu's decoder returns a **list of multiple valid candidates**, proving its theoretical capability to output lists rather than just failing.

---

## 🚀 Getting Started

### Prerequisites
Make sure you have Python 3.8+ installed on your machine.

### Installation

1. **Clone the repository** (if you haven't already):
   ```bash
   git clone <your-repository-url>
   cd List-Decoding-of-QR-codes
   ```

2. **Install the required dependencies:**
   The application requires Streamlit, Pillow (PIL), and the local `qr-list-decoder` math engine.
   ```bash
   pip install streamlit pillow
   
   # Install the local math engine
   pip install -e .
   ```

3. **(Optional but Highly Recommended) Compile the C++ Backend:**
   List decoding involves extremely heavy matrix operations. Compiling the included C++ backend provides a massive speedup and keeps the app responsive.
   ```bash
   pip install pybind11
   python setup.py build_ext --inplace
   ```

### Running the App

To launch the interactive visualizer, simply run:
```bash
streamlit run app.py
```
The app will start a local server and automatically open in your default web browser (typically at `http://localhost:8501`).

---

## 📖 How to Use the App

1. **Configure your QR:** Open the sidebar to type your custom message. Choose the Version and ECC Level. (Higher ECC levels provide a larger padding and error correction margin).
2. **Inspect the Layout:** Scroll down to the Anatomy view to see how your text was transformed into bits, packed into blocks, and scattered across the grid.
3. **Inject Errors:** Go to the "Damage Simulation" section. Use the slider to increase the number of errors. 
4. **Observe the Bounds:** Keep an eye on the Capacity Meter. When the errors exceed the Green zone (Standard BM limit), the BM decoder will fail. If the errors stay within the Blue zone, the Wu Decoder will successfully recover the message!

## License
MIT
