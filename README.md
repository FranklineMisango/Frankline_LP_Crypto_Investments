# Frank-Co LP Crypto Investments

![Python](https://img.shields.io/badge/python-3.8%2B-blue.svg)
![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Contributions](https://img.shields.io/badge/contributions-welcome-brightgreen.svg)

An Algorithmic Research Project to Learn and Develop Potential Strategies, Ghost Patterns, and Advanced Arbitrage that can be exploited in Crypto using Binance as REST.

## Table of Contents

- [Introduction](#introduction)
- [Features](#features)
- [Installation](#installation)
- [Usage](#usage)
- [Contributing](#contributing)
- [License](#license)
- [Contact](#contact)

## Introduction

Frank-Co LP Crypto Investments is a research project focused on developing algorithmic trading strategies for the cryptocurrency market. The project aims to identify and exploit potential strategies, ghost patterns, and advanced arbitrage opportunities using Binance's REST API.

## Features

- **Algorithmic Trading Strategies**: Implement and test various trading strategies.
- **Ghost Pattern Detection**: Identify and analyze ghost patterns in the market.
- **Advanced Arbitrage**: Explore arbitrage opportunities across different exchanges.
- **Data Visualization**: Visualize trading strategies and market data using Plotly.
- **Backtesting**: Backtest strategies using historical data from Binance.

## Installation

To get started with Frank-Co LP Crypto Investments, follow these steps:

1. **Clone the repository**:
    ```bash
    git clone https://github.com/yourusername/Frank-Co_LP_Crypto_Investments.git
    cd Frank-Co_LP_Crypto_Investments
    ```

2. **Create a virtual environment**:
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows use `venv\Scripts\activate`
    ```

3. **Install the required dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

4. **Set up environment variables**:
    Create a `.env` file in the root directory and add your Binance API keys:
    ```env
    Binance_API_KEY=your_api_key
    Binance_secret_KEY=your_secret_key
    ```

## Usage

To run the SMA trading strategy visualization and backtest, use the following command:

```bash
python binance_sma.py