#!/usr/bin/env python3
"""
Live Training Monitor Server (Single File Version)
Run this from your 'model' directory: 
    python live_monitor_server.py
"""

from flask import Flask, jsonify, Response
from flask_cors import CORS
import pandas as pd
import os
import time
import threading

app = Flask(__name__)
CORS(app)

# --- Configuration ---
# Uses the 'logs' folder in the current directory
LOG_DIR = "../../logs/"
CSV_FILE = os.path.join(LOG_DIR, "training_metrics.csv")
REFRESH_INTERVAL = 2  # seconds

# --- Global State ---
latest_data = {
    "metrics": {
        "portfolioValue": 10000.0,
        "winRate": 0.0,
        "totalTrades": 0,
        "maxDrawdown": 0.0,
        "currentDrawdown": 0.0,
        "sharpeRatio": 0.0,
        "timesteps": 0,
        "profitLoss": 0.0,
        "profitPct": 0.0,
        "actionCounts": {"hold": 0, "buy": 0, "sell": 0}
    },
    "trades": [],
    "portfolio_history": [],
    "last_update": 0
}
data_lock = threading.Lock()

# --- Dashboard HTML (Embedded) ---
DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>TickerStream AI - LIVE Dashboard</title>
    <script crossorigin src="https://unpkg.com/react@18/umd/react.production.min.js"></script>
    <script crossorigin src="https://unpkg.com/react-dom@18/umd/react-dom.production.min.js"></script>
    <script src="https://unpkg.com/@babel/standalone/babel.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: linear-gradient(135deg, #0f0c29 0%, #302b63 50%, #24243e 100%);
            color: #e0e0e0;
            min-height: 100vh;
            padding: 20px;
        }
        
        .dashboard {
            max-width: 1800px;
            margin: 0 auto;
        }
        
        .header {
            background: rgba(255, 255, 255, 0.05);
            backdrop-filter: blur(10px);
            border-radius: 16px;
            padding: 24px;
            margin-bottom: 24px;
            border: 1px solid rgba(255, 255, 255, 0.1);
        }
        
        .header h1 {
            font-size: 32px;
            font-weight: 700;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 8px;
        }
        
        .status-bar {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 24px;
            margin-top: 16px;
        }
        
        .status-item {
            display: flex;
            flex-direction: column;
            gap: 4px;
        }
        
        .status-label {
            font-size: 12px;
            text-transform: uppercase;
            letter-spacing: 1px;
            opacity: 0.6;
        }
        
        .status-value {
            font-size: 20px;
            font-weight: 600;
        }
        
        .status-value.positive {
            color: #10b981;
        }
        
        .status-value.negative {
            color: #ef4444;
        }
        
        .status-value.warning {
            color: #f59e0b;
        }
        
        .live-indicator {
            display: flex;
            align-items: center;
            gap: 12px;
            margin-top: 16px;
            padding: 12px 16px;
            background: rgba(16, 185, 129, 0.1);
            border-radius: 8px;
            border: 1px solid rgba(16, 185, 129, 0.3);
        }
        
        .live-indicator.error {
            background: rgba(239, 68, 68, 0.1);
            border-color: rgba(239, 68, 68, 0.3);
        }
        
        .pulse-dot {
            width: 12px;
            height: 12px;
            border-radius: 50%;
            background: #10b981;
            animation: pulse 2s ease-in-out infinite;
        }
        
        .pulse-dot.error {
            background: #ef4444;
            animation: none;
        }
        
        @keyframes pulse {
            0%, 100% { opacity: 1; transform: scale(1); }
            50% { opacity: 0.5; transform: scale(1.2); }
        }
        
        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(450px, 1fr));
            gap: 24px;
            margin-bottom: 24px;
        }
        
        .card {
            background: rgba(255, 255, 255, 0.05);
            backdrop-filter: blur(10px);
            border-radius: 16px;
            padding: 24px;
            border: 1px solid rgba(255, 255, 255, 0.1);
        }
        
        .card-full {
            grid-column: 1 / -1;
        }
        
        .card-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
        }
        
        .card-title {
            font-size: 18px;
            font-weight: 600;
        }
        
        .badge {
            padding: 4px 12px;
            border-radius: 12px;
            font-size: 12px;
            font-weight: 600;
        }
        
        .badge-success {
            background: rgba(16, 185, 129, 0.2);
            color: #10b981;
        }
        
        .badge-warning {
            background: rgba(245, 158, 11, 0.2);
            color: #f59e0b;
        }
        
        .badge-danger {
            background: rgba(239, 68, 68, 0.2);
            color: #ef4444;
        }
        
        .chart-container {
            position: relative;
            height: 300px;
        }
        
        .table-container {
            overflow-x: auto;
            margin-top: 16px;
            max-height: 400px;
            overflow-y: auto;
        }
        
        table {
            width: 100%;
            border-collapse: collapse;
        }
        
        th {
            text-align: left;
            padding: 12px;
            background: rgba(255, 255, 255, 0.05);
            font-weight: 600;
            font-size: 13px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            border-bottom: 2px solid rgba(255, 255, 255, 0.1);
            position: sticky;
            top: 0;
            z-index: 10;
        }
        
        td {
            padding: 12px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.05);
            font-size: 14px;
        }
        
        tr:hover {
            background: rgba(255, 255, 255, 0.03);
        }
        
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 16px;
            margin-top: 16px;
        }
        
        .stat-box {
            background: rgba(255, 255, 255, 0.03);
            padding: 16px;
            border-radius: 12px;
            border: 1px solid rgba(255, 255, 255, 0.05);
            text-align: center;
        }
        
        .stat-label {
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            opacity: 0.6;
            margin-bottom: 8px;
        }
        
        .stat-value {
            font-size: 24px;
            font-weight: 700;
        }
        
        .error-message {
            padding: 16px;
            background: rgba(239, 68, 68, 0.1);
            border: 1px solid rgba(239, 68, 68, 0.3);
            border-radius: 8px;
            margin-top: 16px;
        }
    </style>
</head>
<body>
    <div id="root"></div>

    <script type="text/babel">
        const { useState, useEffect, useRef } = React;

        const API_URL = 'http://localhost:5000/api';
        const REFRESH_INTERVAL = 2000; // 2 seconds

        function TradingDashboard() {
            const [metrics, setMetrics] = useState({
                portfolioValue: 10000,
                winRate: 0,
                totalTrades: 0,
                maxDrawdown: 0,
                currentDrawdown: 0,
                sharpeRatio: 0,
                timesteps: 0,
                profitLoss: 0,
                profitPct: 0,
                actionCounts: { hold: 0, buy: 0, sell: 0 }
            });
            
            const [trades, setTrades] = useState([]);
            const [isConnected, setIsConnected] = useState(false);
            const [lastUpdate, setLastUpdate] = useState(null);
            const [error, setError] = useState(null);
            
            const portfolioChartRef = useRef(null);
            const winRateChartRef = useRef(null);
            const drawdownChartRef = useRef(null);
            const actionPieChartRef = useRef(null);
            
            const chartInstances = useRef({});

            // Initialize Charts
            useEffect(() => {
                const commonOptions = {
                    responsive: true,
                    maintainAspectRatio: false,
                    animation: { duration: 300 },
                    plugins: {
                        tooltip: {
                            backgroundColor: 'rgba(0, 0, 0, 0.8)',
                            padding: 12,
                            titleColor: '#fff',
                            bodyColor: '#e0e0e0'
                        }
                    },
                    scales: {
                        x: {
                            grid: { color: 'rgba(255, 255, 255, 0.05)' },
                            ticks: { color: '#888' }
                        },
                        y: {
                            grid: { color: 'rgba(255, 255, 255, 0.05)' },
                            ticks: { color: '#888' }
                        }
                    }
                };

                // Portfolio Chart
                chartInstances.current.portfolio = new Chart(portfolioChartRef.current, {
                    type: 'line',
                    data: {
                        labels: [],
                        datasets: [{
                            label: 'Portfolio Value',
                            data: [],
                            borderColor: '#667eea',
                            backgroundColor: 'rgba(102, 126, 234, 0.1)',
                            borderWidth: 2,
                            fill: true,
                            tension: 0.4
                        }]
                    },
                    options: {
                        ...commonOptions,
                        plugins: { ...commonOptions.plugins, legend: { display: false } }
                    }
                });

                // Win Rate Chart
                chartInstances.current.winRate = new Chart(winRateChartRef.current, {
                    type: 'line',
                    data: {
                        labels: [],
                        datasets: [{
                            label: 'Win Rate %',
                            data: [],
                            borderColor: '#10b981',
                            backgroundColor: 'rgba(16, 185, 129, 0.1)',
                            borderWidth: 2,
                            fill: true,
                            tension: 0.4
                        }]
                    },
                    options: {
                        ...commonOptions,
                        plugins: { ...commonOptions.plugins, legend: { display: false } },
                        scales: {
                            ...commonOptions.scales,
                            y: {
                                ...commonOptions.scales.y,
                                min: 0,
                                max: 100,
                                ticks: { color: '#888', callback: (value) => value + '%' }
                            }
                        }
                    }
                });

                // Drawdown Chart
                chartInstances.current.drawdown = new Chart(drawdownChartRef.current, {
                    type: 'line',
                    data: {
                        labels: [],
                        datasets: [{
                            label: 'Drawdown %',
                            data: [],
                            borderColor: '#ef4444',
                            backgroundColor: 'rgba(239, 68, 68, 0.1)',
                            borderWidth: 2,
                            fill: true,
                            tension: 0.4
                        }]
                    },
                    options: {
                        ...commonOptions,
                        plugins: { ...commonOptions.plugins, legend: { display: false } }
                    }
                });

                // Action Pie Chart
                chartInstances.current.actionPie = new Chart(actionPieChartRef.current, {
                    type: 'doughnut',
                    data: {
                        labels: ['Hold', 'Buy', 'Sell'],
                        datasets: [{
                            data: [0, 0, 0],
                            backgroundColor: [
                                'rgba(156, 163, 175, 0.6)',
                                'rgba(16, 185, 129, 0.6)',
                                'rgba(239, 68, 68, 0.6)'
                            ],
                            borderColor: ['#9ca3af', '#10b981', '#ef4444'],
                            borderWidth: 2
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        animation: { duration: 300 },
                        plugins: {
                            legend: {
                                position: 'bottom',
                                labels: { color: '#e0e0e0', font: { size: 12 } }
                            },
                            tooltip: {
                                backgroundColor: 'rgba(0, 0, 0, 0.8)',
                                padding: 12,
                                callbacks: {
                                    label: (context) => {
                                        const total = context.dataset.data.reduce((a, b) => a + b, 0);
                                        const percentage = ((context.parsed / total) * 100).toFixed(1);
                                        return `${context.label}: ${context.parsed} (${percentage}%)`;
                                    }
                                }
                            }
                        }
                    }
                });

                return () => {
                    Object.values(chartInstances.current).forEach(chart => chart?.destroy());
                };
            }, []);

            // Fetch data from backend
            const fetchData = async () => {
                try {
                    const response = await fetch(`${API_URL}/all`);
                    
                    if (!response.ok) {
                        throw new Error(`HTTP ${response.status}`);
                    }
                    
                    const data = await response.json();
                    
                    setIsConnected(true);
                    setError(null);
                    setLastUpdate(new Date());
                    
                    // Update metrics
                    if (data.metrics && Object.keys(data.metrics).length > 0) {
                        setMetrics(data.metrics);
                        
                        // Update action pie chart
                        const { hold, buy, sell } = data.metrics.actionCounts || {};
                        chartInstances.current.actionPie.data.datasets[0].data = [hold, buy, sell];
                        chartInstances.current.actionPie.update('none');
                    }
                    
                    // Update trades
                    if (data.trades) {
                        setTrades(data.trades);
                    }
                    
                    // Update portfolio chart
                    if (data.portfolio_history && data.portfolio_history.length > 0) {
                        const labels = data.portfolio_history.map(p => p.timestep);
                        const values = data.portfolio_history.map(p => p.portfolioValue);
                        
                        chartInstances.current.portfolio.data.labels = labels;
                        chartInstances.current.portfolio.data.datasets[0].data = values;
                        chartInstances.current.portfolio.update('none');
                        
                        // Calculate drawdowns for chart
                        const drawdowns = [];
                        let peak = values[0];
                        values.forEach(v => {
                            if (v > peak) peak = v;
                            const dd = ((v - peak) / peak) * 100;
                            drawdowns.push(dd);
                        });
                        
                        chartInstances.current.drawdown.data.labels = labels;
                        chartInstances.current.drawdown.data.datasets[0].data = drawdowns;
                        chartInstances.current.drawdown.update('none');
                        
                        // Win rate approximation (based on positive rewards)
                        const winRates = data.portfolio_history.map((_, idx) => {
                            const windowSize = 20;
                            const start = Math.max(0, idx - windowSize);
                            const window = data.portfolio_history.slice(start, idx + 1);
                            const wins = window.filter(p => p.reward > 0).length;
                            return window.length > 0 ? (wins / window.length) * 100 : 0;
                        });
                        
                        chartInstances.current.winRate.data.labels = labels;
                        chartInstances.current.winRate.data.datasets[0].data = winRates;
                        chartInstances.current.winRate.update('none');
                    }
                    
                } catch (err) {
                    setIsConnected(false);
                    setError(err.message);
                    console.error('Failed to fetch data:', err);
                }
            };

            // Auto-refresh
            useEffect(() => {
                fetchData(); // Initial fetch
                const interval = setInterval(fetchData, REFRESH_INTERVAL);
                return () => clearInterval(interval);
            }, []);

            const drawdownBadge = Math.abs(metrics.currentDrawdown) > 10 ? 'badge-danger' : 
                                   Math.abs(metrics.currentDrawdown) > 5 ? 'badge-warning' : 'badge-success';

            return (
                <div className="dashboard">
                    <div className="header">
                        <h1>🔴 LIVE Training Dashboard</h1>
                        <p style={{ opacity: 0.7, marginTop: 4 }}>Real-time monitoring from your training logs</p>
                        
                        <div className={`live-indicator ${!isConnected ? 'error' : ''}`}>
                            <div className={`pulse-dot ${!isConnected ? 'error' : ''}`}></div>
                            <div style={{ flex: 1 }}>
                                <div style={{ fontWeight: 600 }}>
                                    {isConnected ? '🟢 Connected to Training Server' : '🔴 Disconnected'}
                                </div>
                                <div style={{ fontSize: 12, opacity: 0.7, marginTop: 4 }}>
                                    {lastUpdate ? `Last update: ${lastUpdate.toLocaleTimeString()}` : 'Waiting for data...'}
                                </div>
                            </div>
                            <div style={{ fontSize: 12, opacity: 0.7 }}>
                                Refreshing every {REFRESH_INTERVAL/1000}s
                            </div>
                        </div>
                        
                        {error && (
                            <div className="error-message">
                                <strong>⚠️ Connection Error:</strong> {error}
                                <br />
                                <small>Make sure the server is running: <code>python live_monitor_server.py</code></small>
                            </div>
                        )}
                        
                        <div className="status-bar">
                            <div className="status-item">
                                <div className="status-label">Portfolio Value</div>
                                <div className={`status-value ${metrics.profitLoss >= 0 ? 'positive' : 'negative'}`}>
                                    ${metrics.portfolioValue.toFixed(2)}
                                </div>
                            </div>
                            <div className="status-item">
                                <div className="status-label">P/L</div>
                                <div className={`status-value ${metrics.profitLoss >= 0 ? 'positive' : 'negative'}`}>
                                    {metrics.profitLoss >= 0 ? '+' : ''}{metrics.profitPct.toFixed(2)}%
                                </div>
                            </div>
                            <div className="status-item">
                                <div className="status-label">Win Rate</div>
                                <div className="status-value">
                                    {metrics.winRate.toFixed(1)}%
                                </div>
                            </div>
                            <div className="status-item">
                                <div className="status-label">Max Drawdown</div>
                                <div className="status-value negative">
                                    {metrics.maxDrawdown.toFixed(2)}%
                                </div>
                            </div>
                            <div className="status-item">
                                <div className="status-label">Current DD</div>
                                <div className={`status-value ${Math.abs(metrics.currentDrawdown) > 5 ? 'warning' : ''}`}>
                                    {metrics.currentDrawdown.toFixed(2)}%
                                </div>
                            </div>
                            <div className="status-item">
                                <div className="status-label">Sharpe Ratio</div>
                                <div className="status-value positive">
                                    {metrics.sharpeRatio.toFixed(2)}
                                </div>
                            </div>
                            <div className="status-item">
                                <div className="status-label">Total Trades</div>
                                <div className="status-value">
                                    {metrics.totalTrades}
                                </div>
                            </div>
                            <div className="status-item">
                                <div className="status-label">Timesteps</div>
                                <div className="status-value">
                                    {metrics.timesteps.toLocaleString()}
                                </div>
                            </div>
                        </div>
                    </div>

                    <div className="grid">
                        <div className="card">
                            <div className="card-header">
                                <div className="card-title">Portfolio Value Over Time</div>
                                <div className="badge badge-success">Live</div>
                            </div>
                            <div className="chart-container">
                                <canvas ref={portfolioChartRef}></canvas>
                            </div>
                        </div>

                        <div className="card">
                            <div className="card-header">
                                <div className="card-title">Drawdown Analysis</div>
                                <div className={`badge ${drawdownBadge}`}>
                                    {Math.abs(metrics.maxDrawdown).toFixed(1)}% Max
                                </div>
                            </div>
                            <div className="chart-container">
                                <canvas ref={drawdownChartRef}></canvas>
                            </div>
                        </div>
                    </div>

                    <div className="grid">
                        <div className="card">
                            <div className="card-header">
                                <div className="card-title">Win Rate Evolution</div>
                                <div className="badge badge-success">Live</div>
                            </div>
                            <div className="chart-container">
                                <canvas ref={winRateChartRef}></canvas>
                            </div>
                        </div>

                        <div className="card">
                            <div className="card-header">
                                <div className="card-title">Action Distribution</div>
                                <div className="badge badge-success">
                                    {metrics.totalTrades} trades
                                </div>
                            </div>
                            <div className="chart-container">
                                <canvas ref={actionPieChartRef}></canvas>
                            </div>
                            <div className="stats-grid">
                                <div className="stat-box">
                                    <div className="stat-label">Hold</div>
                                    <div className="stat-value" style={{ color: '#9ca3af' }}>
                                        {metrics.actionCounts.hold}
                                    </div>
                                </div>
                                <div className="stat-box">
                                    <div className="stat-label">Buy</div>
                                    <div className="stat-value" style={{ color: '#10b981' }}>
                                        {metrics.actionCounts.buy}
                                    </div>
                                </div>
                                <div className="stat-box">
                                    <div className="stat-label">Sell</div>
                                    <div className="stat-value" style={{ color: '#ef4444' }}>
                                        {metrics.actionCounts.sell}
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>

                    <div className="card card-full">
                        <div className="card-header">
                            <div className="card-title">Recent Trades</div>
                            <div className="badge badge-success">{trades.length} trades</div>
                        </div>

                        <div className="table-container">
                            <table>
                                <thead>
                                    <tr>
                                        <th>Timestep</th>
                                        <th>Ticker</th>
                                        <th>Action</th>
                                        <th>Portfolio Value</th>
                                        <th>Balance</th>
                                        <th>Reward</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {trades.slice(0, 50).map((trade, idx) => (
                                        <tr key={idx}>
                                            <td>{trade.timestep}</td>
                                            <td style={{ fontWeight: 600 }}>{trade.ticker}</td>
                                            <td>
                                                <span style={{ 
                                                    color: trade.action === 'BUY' ? '#10b981' : '#ef4444',
                                                    fontWeight: 600
                                                }}>
                                                    {trade.action}
                                                </span>
                                            </td>
                                            <td>${trade.portfolioValue.toFixed(2)}</td>
                                            <td>${trade.balance.toFixed(2)}</td>
                                            <td>
                                                <span style={{
                                                    color: trade.reward > 0 ? '#10b981' : trade.reward < 0 ? '#ef4444' : '#888',
                                                    fontWeight: 600
                                                }}>
                                                    {(trade.reward).toFixed(0)}
                                                </span>
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                            {trades.length === 0 && (
                                <div style={{ textAlign: 'center', padding: '40px', opacity: 0.5 }}>
                                    No trades yet. Start training to see activity here.
                                </div>
                            )}
                        </div>
                    </div>
                </div>
            );
        }

        ReactDOM.render(<TradingDashboard />, document.getElementById('root'));
    </script>
</body>
</html>
"""

# --- Logic ---

def calculate_metrics(df):
    if df.empty: return None
    try:
        portfolio_values = df['portfolio_value'].values
        latest_pv = float(df['portfolio_value'].iloc[-1])
        initial_pv = 10000
        
        peak = pd.Series(portfolio_values).expanding().max()
        drawdown = ((pd.Series(portfolio_values) - peak) / peak * 100).values
        max_dd = float(drawdown.min())
        current_dd = float(drawdown[-1])
        
        window_size = 50
        win_rate = 0.0
        if len(df) > window_size:
            recent_rewards = df['reward'].iloc[-window_size:]
            win_rate = float((recent_rewards > 0).sum() / len(recent_rewards) * 100)
        
        actions = df['action'].value_counts()
        action_counts = {'hold': int(actions.get(0, 0)), 'buy': int(actions.get(1, 0)), 'sell': int(actions.get(2, 0))}
        total_trades = action_counts['buy'] + action_counts['sell']
        
        returns = pd.Series(portfolio_values).pct_change().dropna()
        sharpe = float((returns.mean() / (returns.std() + 1e-8)) * (252 ** 0.5)) if len(returns) > 0 else 0.0
        
        return {
            "portfolioValue": latest_pv, "winRate": win_rate, "totalTrades": total_trades,
            "maxDrawdown": max_dd, "currentDrawdown": current_dd, "sharpeRatio": sharpe,
            "timesteps": int(df['timestep'].iloc[-1]), "actionCounts": action_counts,
            "profitLoss": latest_pv - initial_pv, "profitPct": ((latest_pv - initial_pv) / initial_pv) * 100
        }
    except Exception as e:
        print(f"Metrics Error: {e}")
        return None

def get_recent_trades(df, limit=50):
    if df.empty: return []
    try:
        trades_df = df[df['action'].isin([1, 2])].tail(limit)
        return [{
            "timestep": int(row['timestep']),
            "ticker": str(row['ticker']),
            "action": "BUY" if row['action'] == 1 else "SELL",
            "portfolioValue": float(row['portfolio_value']),
            "balance": float(row['balance']),
            "reward": float(row.get('reward', 0))
        } for _, row in trades_df.iterrows()]
    except Exception: return []

def get_portfolio_history(df, max_points=100):
    if df.empty: return []
    try:
        df_sampled = df.iloc[::(len(df) // max_points)] if len(df) > max_points else df
        return [{
            "timestep": int(row['timestep']),
            "portfolioValue": float(row['portfolio_value']),
            "reward": float(row.get('reward', 0))
        } for _, row in df_sampled.iterrows()]
    except Exception: return []

def monitor_logs():
    print(f"📊 Monitoring logs directory: {LOG_DIR}")
    last_mtime = 0
    global latest_data
    while True:
        try:
            if os.path.exists(CSV_FILE):
                current_mtime = os.path.getmtime(CSV_FILE)
                # if current_mtime > last_mtime:
                df = pd.read_csv(CSV_FILE)
                if not df.empty:
                    metrics = calculate_metrics(df)
                    if metrics:
                        with data_lock:
                            print()
                            latest_data = {
                                "metrics": metrics,
                                "trades": get_recent_trades(df),
                                "portfolio_history": get_portfolio_history(df),
                                "last_update": time.time()
                            }

                        print(f"✅ Updated: PV=${metrics['portfolioValue']:.2f} WR={metrics['winRate']:.1f}%")
                else:
                    print("Failed to load csv from: {CSV_FILE}")
                last_mtime = current_mtime
                time.sleep(60) # Sleep for one minute
            time.sleep(REFRESH_INTERVAL)
        except Exception as e:
            print(f"❌ Error: {e}")
            time.sleep(REFRESH_INTERVAL)

# --- Routes ---

@app.route('/')
def dashboard():
    return DASHBOARD_HTML

@app.route('/api/all')
def get_all():
    with data_lock:
        return jsonify(latest_data)

if __name__ == '__main__':
    print("🚀 Starting Live Monitor...")
    threading.Thread(target=monitor_logs, daemon=True).start()
    app.run(host='0.0.0.0', port=5000)