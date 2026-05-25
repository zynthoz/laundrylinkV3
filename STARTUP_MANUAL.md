# LaundryLink Local Development & Startup Manual

This document provides step-by-step instructions for running the LaundryLink application locally, managing test data (seeding/wiping dummy data), and navigating the project structure on both Windows and Linux.

---

## 1. Prerequisites & Preparation

Before starting the app, ensure you have Python (version 3.8+) installed.

First, open your terminal and navigate to the `laundrylinkV2` backend directory to install the necessary Python dependencies.

**For Windows:**
```powershell
# Navigate to the backend directory
cd "C:\path\to\laundrylinkV3\laundrylinkV2"

# Install backend dependencies
python -m pip install -r requirements.txt
```

**For Linux / macOS:**
```bash
# Navigate to the backend directory
cd /path/to/laundrylinkV3/laundrylinkV2

# Install backend dependencies (you may need to use python3/pip3)
python3 -m pip install -r requirements.txt
```

---

## 2. Managing Dummy Data

The project includes a dummy data generator script (`seed_dummy_data.py`) located in the backend folder (`laundrylinkV2`). This script handles injecting fake customers, shifts, transactions, and performance metrics for testing purposes.

### A. Populate Data (Standard Seed)
This generates 30 days of historical dummy records. *Note: It automatically backups the current database and safely clears old dummy data before injecting the new data to prevent duplicates.*

**Windows:**
```powershell
cd "C:\path\to\laundrylinkV3\laundrylinkV2"
python seed_dummy_data.py
```

**Linux:**
```bash
cd /path/to/laundrylinkV3/laundrylinkV2
python3 seed_dummy_data.py
```

### B. Wipe Dummy Data (`--wipe`)
If you want to clear out the dummy data (transactions, shift sessions, customers, manual expenses) while keeping your core local machine settings intact, pass the `--wipe` flag.

**Windows:**
```powershell
python seed_dummy_data.py --wipe
```

**Linux:**
```bash
python3 seed_dummy_data.py --wipe
```

### C. Restore Database (`--restore`)
If you want to revert your database to the exact original clean state it was in before you injected dummy data for the very first time, use the restore flag.

**Windows:**
```powershell
python seed_dummy_data.py --restore
```

**Linux:**
```bash
python3 seed_dummy_data.py --restore
```

---

## 3. Starting the Application

The application requires running both the **Backend API** and the **Frontend Web Server** at the same time. You will need to open **two separate terminal windows**.

### Terminal 1: Start the Backend (API Server)

The backend handles the hardware controls, database logic, and API routes. It will start on **port 5000**.

**Windows:**
```powershell
# Open terminal 1 and go into the backend folder
cd "C:\path\to\laundrylinkV3\laundrylinkV2"

# Start the Flask API
python app.py
```

**Linux:**
```bash
# Open terminal 1 and go into the backend folder
cd /path/to/laundrylinkV3/laundrylinkV2

# Start the Flask API
python3 app.py
```
*(Leave this terminal running in the background).*

### Terminal 2: Start the Frontend (Web Server)

The frontend consists of static HTML/JS/CSS files. You need a simple web server to serve these files so the browser runs them correctly (preventing secure connection/CORS issues). It will start on **port 8000**.

**Windows:**
```powershell
# Open terminal 2 and go into the frontend folder
cd "C:\path\to\laundrylinkV3\laundrylink-frontend"

# Start a simple Python HTTP server
python -m http.server 8000
```

**Linux:**
```bash
# Open terminal 2 and go into the frontend folder
cd /path/to/laundrylinkV3/laundrylink-frontend

# Start a simple Python HTTP server
python3 -m http.server 8000
```
*(Leave this terminal running in the background).*

---

## 4. Accessing the App

Once both terminals are actively running, open your web browser (Chrome/Edge/Firefox/Safari) and go to:

👉 **http://localhost:8000**

- The frontend will automatically detect that it's running locally and connect internally to the backend API at `http://127.0.0.1:5000/api`.
- The dummy data and UI panels should load smoothly without API connection errors.
- **Tunneling Compatibility**: Running tunneling software (like Ngrok, Cloudflare Tunnels, Localtonet) over port `5000` (for backend apps) or `8000` (for frontend hosting) functions independently of your local database data, and will safely stream out whatever dummy data (or wiped clean slate) you currently have populated!