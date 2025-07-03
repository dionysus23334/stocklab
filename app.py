from flask import Flask, render_template, request, jsonify, flash, redirect, url_for, abort, Response
import pandas as pd
import numpy as np
import json
import os
from datetime import datetime, timedelta
import ta
import io
import sys
from contextlib import redirect_stdout, redirect_stderr
from io import BytesIO
from io import StringIO

from data_collection.stock_data import *

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

@app.route('/stock/<string:symbol>/<string:period>', methods=['POST','GET'])
def get_stock_data(symbol, period):
    period_map = {
        "1mo": 30,
        "3mo": 90,
        "6mo": 180,
        "1y": 365,
        "2y": 730
    }
    days = period_map.get(period, 365)
    
    try:
        # 这里调用你的爬虫函数
        result_json = get_complete_data([symbol], days)  # 返回JSON字符串
        stock_data = json.loads(result_json)
        if not stock_data:
            abort(404, description="未找到该股票数据")
    except Exception as e:
        abort(500, description=f"服务器错误: {str(e)}")
    
    # 把stock_data传给模板，模板用Jinja渲染
    # 这里json.dumps转回字符串，方便在js里直接用
    return render_template('stock_detail.html', symbol=symbol, period=period, stock_data=stock_data)

@app.route('/download/<symbol>/<period>')
def download_stock_data(symbol, period):
    try:
        fmt = request.args.get("format", "csv")  # 默认csv
        period_map = {
            "1mo": 30,
            "3mo": 90,
            "6mo": 180,
            "1y": 365,
            "2y": 730
        }
        days = period_map.get(period, 365)

        result_json = get_complete_data([symbol], days)
        stock_data = json.loads(result_json)

        if not stock_data:
            abort(404, description="没有找到数据")

        import pandas as pd
        df = pd.DataFrame(stock_data)

        if fmt == "xlsx":

            output = BytesIO()
            df.to_excel(output, index=False)
            output.seek(0)
            return Response(
                output,
                mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                headers={"Content-Disposition": f"attachment;filename={symbol}_{period}.xlsx"}
            )
        else:
            # 默认为csv

            output = StringIO()
            df.to_csv(output, index=False, encoding='utf-8-sig')
            output.seek(0)
            return Response(
                output,
                mimetype="text/csv",
                headers={"Content-Disposition": f"attachment;filename={symbol}_{period}.csv"}
            )

    except Exception as e:
        abort(500, description=f"服务器错误: {str(e)}")



# 布林通道策略
def calculate_bollinger(df, window=20, num_std=2):
    df['MA'] = df['收盘价'].rolling(window).mean()
    df['STD'] = df['收盘价'].rolling(window).std()
    df['upper'] = df['MA'] + num_std * df['STD']
    df['lower'] = df['MA'] - num_std * df['STD']
    return df 

@app.route('/bollinger/<symbol>/<period>')
def bollinger_chart(symbol, period):
    days_map = {
        "1mo": 30, "3mo": 90, "6mo": 180, "1y": 365, "2y": 730
    }
    days = days_map.get(period, 365)

    result_json = get_complete_data([symbol], days)
    data = json.loads(result_json)
    df = pd.DataFrame(data)
    df = calculate_bollinger(df)

    # 先提取股票名称
    stock_name = df['股票名称'].iloc[0] if '股票名称' in df.columns else "未知股票"

    # 图表只传必须字段
    chart_data = df[['日期', '开盘价', '最高价', '最低价', '收盘价', 'upper', 'lower']].to_dict(orient="records")

    return render_template(
        'bollinger.html',
        symbol=symbol,
        period=period,
        stock_name=stock_name,
        chart_data_json=json.dumps(chart_data, ensure_ascii=False)
    )


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