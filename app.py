from flask import Flask, render_template, request, jsonify, flash, redirect, url_for
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objs as go
import plotly.utils
import json
import os
from datetime import datetime, timedelta
import ta
import io
import sys
from contextlib import redirect_stdout, redirect_stderr

app = Flask(__name__)
app.secret_key = 'your-secret-key-here'

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/crawler')
def crawler():
    return render_template('crawler.html')

@app.route('/stock_selection')
def stock_selection():
    return render_template('stock_selection.html')

@app.route('/backtest')
def backtest():
    return render_template('backtest.html')

@app.route('/api/get_stock_data', methods=['POST'])
def get_stock_data():
    try:
        data = request.get_json()
        symbol = data.get('symbol', '').strip()
        period = data.get('period', '1y')
        
        if not symbol:
            return jsonify({'error': '请输入股票代码或名称'}), 400
        
        # 获取股票数据
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period=period)
        
        if hist.empty:
            return jsonify({'error': '未找到该股票数据，请检查股票代码'}), 404
        
        # 获取股票信息
        info = ticker.info
        
        # 计算技术指标
        hist['SMA_20'] = ta.trend.sma_indicator(hist['Close'], window=20)
        hist['SMA_50'] = ta.trend.sma_indicator(hist['Close'], window=50)
        hist['RSI'] = ta.momentum.rsi(hist['Close'])
        hist['MACD'] = ta.trend.macd_diff(hist['Close'])
        
        # 准备图表数据
        trace1 = go.Candlestick(
            x=hist.index,
            open=hist['Open'],
            high=hist['High'],
            low=hist['Low'],
            close=hist['Close'],
            name='K线图'
        )
        
        trace2 = go.Scatter(
            x=hist.index,
            y=hist['SMA_20'],
            name='SMA 20',
            line=dict(color='orange')
        )
        
        trace3 = go.Scatter(
            x=hist.index,
            y=hist['SMA_50'],
            name='SMA 50',
            line=dict(color='blue')
        )
        
        fig = go.Figure(data=[trace1, trace2, trace3])
        fig.update_layout(
            title=f'{symbol} 股票价格走势',
            yaxis_title='价格',
            xaxis_title='日期',
            template='plotly_dark'
        )
        
        graphJSON = json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)
        
        # 准备返回数据
        latest_data = hist.iloc[-1]
        stock_data = {
            'symbol': symbol,
            'name': info.get('longName', symbol),
            'current_price': round(latest_data['Close'], 2),
            'change': round(latest_data['Close'] - hist.iloc[-2]['Close'], 2),
            'change_percent': round(((latest_data['Close'] - hist.iloc[-2]['Close']) / hist.iloc[-2]['Close']) * 100, 2),
            'volume': int(latest_data['Volume']),
            'market_cap': info.get('marketCap', 'N/A'),
            'pe_ratio': info.get('trailingPE', 'N/A'),
            'rsi': round(latest_data['RSI'], 2) if pd.notna(latest_data['RSI']) else 'N/A',
            'chart': graphJSON
        }
        
        return jsonify(stock_data)
        
    except Exception as e:
        return jsonify({'error': f'获取数据失败: {str(e)}'}), 500

@app.route('/api/screen_stocks', methods=['POST'])
def screen_stocks():
    try:
        data = request.get_json()
        
        # 示例股票列表（实际应用中可以从数据库或API获取更多股票）
        symbols = [
            '000001.SZ', '000002.SZ', '600000.SS', '600036.SS', '600519.SS',
            '000858.SZ', '002415.SZ', '300059.SZ', '002594.SZ', '600276.SS'
        ]
        
        criteria = {
            'min_price': float(data.get('min_price', 0)),
            'max_price': float(data.get('max_price', 1000000)),
            'min_volume': int(data.get('min_volume', 0)),
            'max_rsi': float(data.get('max_rsi', 100)),
            'min_rsi': float(data.get('min_rsi', 0))
        }
        
        filtered_stocks = []
        
        for symbol in symbols:
            try:
                ticker = yf.Ticker(symbol)
                hist = ticker.history(period='1mo')
                
                if not hist.empty:
                    latest = hist.iloc[-1]
                    rsi = ta.momentum.rsi(hist['Close']).iloc[-1]
                    
                    # 应用筛选条件
                    if (criteria['min_price'] <= latest['Close'] <= criteria['max_price'] and
                        latest['Volume'] >= criteria['min_volume'] and
                        criteria['min_rsi'] <= rsi <= criteria['max_rsi']):
                        
                        info = ticker.info
                        filtered_stocks.append({
                            'symbol': symbol,
                            'name': info.get('longName', symbol)[:20] + '...' if len(info.get('longName', symbol)) > 20 else info.get('longName', symbol),
                            'price': round(latest['Close'], 2),
                            'volume': int(latest['Volume']),
                            'rsi': round(rsi, 2) if pd.notna(rsi) else 'N/A'
                        })
                        
            except Exception as e:
                continue
        
        return jsonify({'stocks': filtered_stocks[:20]})  # 限制返回数量
        
    except Exception as e:
        return jsonify({'error': f'筛选失败: {str(e)}'}), 500

@app.route('/api/run_backtest', methods=['POST'])
def run_backtest():
    try:
        data = request.get_json()
        code = data.get('code', '')
        symbol = data.get('symbol', '000001.SZ')
        
        if not code:
            return jsonify({'error': '请输入回测代码'}), 400
        
        # 获取股票数据供回测使用
        ticker = yf.Ticker(symbol)
        stock_data = ticker.history(period='1y')
        
        # 创建安全的执行环境
        safe_globals = {
            '__builtins__': {
                'print': print,
                'len': len,
                'range': range,
                'round': round,
                'max': max,
                'min': min,
                'sum': sum,
                'abs': abs
            },
            'pd': pd,
            'np': np,
            'ta': ta,
            'data': stock_data,
            'symbol': symbol
        }
        
        # 捕获输出
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        
        stdout_buffer = io.StringIO()
        stderr_buffer = io.StringIO()
        
        try:
            sys.stdout = stdout_buffer
            sys.stderr = stderr_buffer
            
            # 执行用户代码
            exec(code, safe_globals)
            
            output = stdout_buffer.getvalue()
            error = stderr_buffer.getvalue()
            
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr
        
        if error:
            return jsonify({'error': f'代码执行错误: {error}'}), 400
        
        return jsonify({
            'output': output if output else '代码执行完成，无输出结果',
            'symbol': symbol
        })
        
    except Exception as e:
        return jsonify({'error': f'回测失败: {str(e)}'}), 500

if __name__ == '__main__':
    app.run(debug=True)