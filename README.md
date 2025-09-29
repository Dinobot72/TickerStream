# Stock-Bot 🤖

**Stock-Bot** is a comprehensive, full-stack application that leverages a deep reinforcement learning model to perform automated stock trading. It features a Python-based backend with a machine learning model for decision-making, and a TypeScript-based frontend for user interaction.

## ✨ Key Features

* **🤖 Automated Trading Bot:** A Proximal Policy Optimization (PPO) model, built with `stable-baselines3`, analyzes market data and your portfolio to make trading decisions (BUY, SELL, HOLD).
* **🖥️ Interactive Dashboard:** The Angular frontend provides a user-friendly interface to monitor stock performance, view portfolio summaries, and check the bot's status in real time.
* **⚡️ Real-time Stock Data:** The FastAPI backend fetches live stock market data using the `yfinance` library, ensuring that the trading bot and the user have access to the latest information.
* **📦 Scalable Backend:** The backend is built with FastAPI, providing a high-performance, scalable, and asynchronous API.
* **📂 Portfolio Management:** The application uses an SQLite database to store and manage user portfolio data, tracking holdings and performance over time.

## 🛠️ Technologies Used

### **Frontend**
* **Angular**
* **TypeScript**
* **Tailwind CSS**
* **Express.js**

### **Backend**
* **FastAPI**
* **Python**
* **yfinance**
* **SQLite**

### **Machine Learning**
* **Stable Baselines3**
* **PyTorch**
* **Gymnasium**
* **Pandas**
* **NumPy**

## 🚀 Getting Started

### **Prerequisites**

-   **Node.js and npm:** For the frontend.
-   **Python 3.8+ and pip:** For the backend and machine learning model.
-   **Gradle:** For building the project.

### **Installation & Setup**

1.  **Clone the repository:**
    ```bash
    git clone [https://github.com/your-username/stock-bot.git](https://github.com/your-username/stock-bot.git)
    cd stock-bot
    ```

2.  **Backend Setup:**
    ```bash
    cd backend
    pip install -r requirements.txt
    ```

3.  **Frontend Setup:**
    ```bash
    cd ../frontend
    npm install
    ```

4.  **Model Setup:**
    ```bash
    cd ../model
    pip install -r requirements.txt
    ```

### **Running the Application**

1.  **Start the Backend Server:**
    ```bash
    cd backend
    uvicorn app.main:app --reload
    ```
    The backend will be available at `http://localhost:8000`.

2.  **Start the Frontend Development Server:**
    ```bash
    cd ../frontend
    ng serve
    ```
    The frontend will be available at `http://localhost:4200`.

3.  **Build the Entire Project:**
    ```bash
    gradle buildAll
    ```

## 🧠 How the Trading Bot Works

The core of this project is the **PPO (Proximal Policy Optimization)** trading bot. The bot is trained on historical stock data to learn a profitable trading strategy.

1.  **Data Preparation:** The `data_prep.py` script downloads historical stock data from Yahoo Finance.
2.  **Custom Environment:** `trading_env.py` creates a custom environment using `gymnasium`, where the bot can simulate trading.
3.  **Training:** The `train_model.py` script uses this environment to train the PPO model.
4.  **Decision Making:** The trained model is loaded by the `strategy_engine.py`, which provides an endpoint for the FastAPI backend to get trading decisions.
