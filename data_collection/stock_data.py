import requests
import pandas as pd
import time
from fake_useragent import UserAgent

# 字段映射（API字段到中文）——加入了换手率 f61
mapping_field = {
    'f51': '日期',
    'f52': '开盘价',
    'f53': '收盘价',
    'f54': '最高价',
    'f55': '最低价',
    'f56': '成交量',
    'f57': '成交额',
    'f58': '振幅',
    'f59': '涨跌幅',
    'f60': '涨跌额',
    'f61': '换手率'   # ✅ 加入换手率
}

class EastmoneyKlineFetcher:
    def __init__(self, stock_list, klt="101", fqt="1", lmt=120):
        self.ua = UserAgent()
        self.stock_list = stock_list  # 格式如：['0.002040', '1.600519']
        self.klt = klt  # K线类型
        self.fqt = fqt  # 复权方式
        self.lmt = lmt  # 数据条数限制

    def fetch_single(self, stock_code):

        headers = {
            "User-Agent": self.ua.random,
            "Referer": "https://quote.eastmoney.com/",
            'Accept-Language':'zh-CN,zh;q=0.9'
        }

        # headers['User-Agent']='Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/55.0.2883.87 Safari/537.36'

        # 构造secid参数
        market = "1" if stock_code.startswith(('6', '5')) else "0"
        secid = f"{market}.{stock_code}"
        url = (
            f"https://push2his.eastmoney.com/api/qt/stock/kline/get?"
            f"secid={secid}&ut=fa5fd1943c7b386f172d6893dbfba10b"
            f"&fields1=f1,f2,f3,f4,f5,f6"
            f"&fields2={','.join(mapping_field.keys())}"
            f"&klt={self.klt}&fqt={self.fqt}&end=20500101&lmt={self.lmt}"
        )
        try:
            response = requests.get(url, headers=headers, timeout=10)
            json_data = response.json()
            if not json_data.get("data"):
                print(f"Warning: No data for {secid}")
                return None
            klines = json_data["data"]["klines"]
            df = pd.DataFrame(
                [line.split(',') for line in klines],
                columns=list(mapping_field.values())
            )
            df["股票代码"] = stock_code
            return df
        except Exception as e:
            print(f"Error fetching {secid}: {e}")
            return None

    def fetch_all(self):
        all_data = []
        for stock_code in self.stock_list:
            print(f"Fetching: {stock_code}")
            df = self.fetch_single(stock_code)
            if df is not None:
                all_data.append(df)
            time.sleep(0.5)  # 防止触发限速
        return pd.concat(all_data, ignore_index=True) if all_data else None
    

# 资金流向字段映射（根据实际API响应调整）
money_flow_mapping = {
    0: '日期',
    1: '主力净流入(元)',
    2: '小单净流入(元)',
    3: '中单净流入(元)',
    4: '大单净流入(元)',
    5: '超大单净流入(元)',
    6: '主力净流入占比(%)',
    7: '小单净流入占比(%)',
    8: '中单净流入占比(%)',
    9: '大单净流入占比(%)',
    10: '超大单净流入占比(%)',
    11: '收盘价',
    12: '涨跌幅(%)'
}

class EastMoneyDailyMoneyFlowFetcher:
    def __init__(self, stock_codes, days=5):
        self.ua = UserAgent()
        self.stock_codes = stock_codes
        self.days = days
        
    def fetch_single(self, stock_code):
        headers = {
            "User-Agent": self.ua.random,
            "Referer": "https://data.eastmoney.com/",
            'Accept-Language':'zh-CN,zh;q=0.9'
        }

        # headers['User-Agent']='Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/55.0.2883.87 Safari/537.36'

        market = "1" if stock_code.startswith(('6', '5')) else "0"
        secid = f"{market}.{stock_code}"
        
        url = (
            f"https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get?"
            f"secid={secid}"
            f"&fields1=f1,f2,f3,f7"
            f"&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63"
            f"&klt=101"  # 日线数据
            f"&lmt={self.days}"
            f"&ut=b2884a393a59ad64002292a3e90d46a5"
        )
        
        try:
            response = requests.get(url, headers=headers, timeout=10)
            json_data = response.json()
            if json_data.get("rc") != 0 or not json_data.get("data"):
                print(f"Warning: No data for {stock_code}")
                return None
                
            data = json_data["data"]
            klines = data["klines"]
            
            if not klines:
                return None
                
            # 处理数据
            all_data = []
            for line in klines:
                values = line.split(',')
                if len(values) != len(money_flow_mapping):
                    print(f"数据列数不匹配: 预期{len(money_flow_mapping)}列，实际{len(values)}列")
                    continue
                row_data = {desc: values[i] for i, desc in money_flow_mapping.items()}
                row_data["股票代码"] = stock_code
                row_data["股票名称"] = data.get("name", "")
                all_data.append(row_data)
                
            df = pd.DataFrame(all_data)
            return df
            
        except Exception as e:
            print(f"Error fetching {stock_code}: {e}")
            return None
    
    def fetch_all(self):
        all_data = []
        for i, code in enumerate(self.stock_codes):
            print(f"第{i}支股票:")
            print(f"Fetching daily money flow for: {code}")
            df = self.fetch_single(code)
            if df is not None:
                all_data.append(df)
            # time.sleep(1)  # 防止触发限速
        return pd.concat(all_data, ignore_index=True) if all_data else None


def get_complete_data(stock_list, days):

    fetcher1 = EastmoneyKlineFetcher(stock_list, klt='101', fqt='1', lmt=days)
    df1 = fetcher1.fetch_all()
    fetcher2 = EastMoneyDailyMoneyFlowFetcher(stock_list, days=days)
    df2 = fetcher2.fetch_all()

    # 第一步：统一“日期”列的格式（建议转成 datetime 类型）
    df1["日期"] = pd.to_datetime(df1["日期"])
    df2["日期"] = pd.to_datetime(df2["日期"])

    # 第二步：统一“股票代码”的格式
    df1["股票代码"] = df1["股票代码"].astype(str)
    df2["股票代码"] = df2["股票代码"].astype(str)

    # 第三步：合并两个 DataFrame（按日期和股票代码对齐）
    merged_df = pd.merge(df2, df1, on=["日期", "股票代码"], how="outer", suffixes=('_kline', '_flow'))
    
    # 排序：日期近的在上
    merged_df.sort_values(by=["股票代码", "日期"], ascending=[True, False], inplace=True)

    # 可选：重置索引
    merged_df.reset_index(drop=True, inplace=True)

    # df 是你合并后的 merged_df
    df = merged_df

    # 先生成一个统一的收盘价列
    # 优先取收盘价_kline，如果为空则用收盘价_flow
    df["收盘价"] = df["收盘价_kline"].combine_first(df["收盘价_flow"])

    # 删除原先的两个列
    df.drop(columns=["收盘价_kline", "收盘价_flow"], inplace=True, errors="ignore")

    df["日期"] = df["日期"].dt.strftime("%Y-%m-%d")

    # 重新指定列的顺序
    final_columns = [
        '日期', '股票代码', '股票名称',
        '开盘价', '收盘价', '最高价', '最低价',
        '成交量', '成交额', '换手率', '振幅', '涨跌幅', '涨跌额',
        '主力净流入(元)', '小单净流入(元)', '中单净流入(元)',
        '大单净流入(元)', '超大单净流入(元)',
        '主力净流入占比(%)', '小单净流入占比(%)', '中单净流入占比(%)',
        '大单净流入占比(%)', '超大单净流入占比(%)'
    ]

    numeric_columns = [
        "开盘价", "收盘价", "最高价", "最低价", 
        "成交量", "成交额", "换手率", "振幅", "涨跌幅", "涨跌额",
        "主力净流入(元)", "小单净流入(元)", "中单净流入(元)",
        "大单净流入(元)", "超大单净流入(元)",
        "主力净流入占比(%)", "小单净流入占比(%)", "中单净流入占比(%)",
        "大单净流入占比(%)", "超大单净流入占比(%)"
    ]


    for col in numeric_columns:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # 有些列可能缺失，比如涨跌额，你可以在这里做一个交集
    final_columns = [col for col in final_columns if col in df.columns]

    # 重排
    df = df[final_columns]

    # 先找到第一个非空的股票名称
    first_name = df['股票名称'].dropna().iloc[0]

    # 再整体填充
    df['股票名称'] = df['股票名称'].fillna(first_name)

    # 转换为 json
    result_json = df.to_json(orient="records", force_ascii=False)

    # 显示结果
    return result_json





if __name__ == '__main__':

    data = get_complete_data(['001317'], 90)

