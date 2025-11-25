import streamlit as st
import yfinance as yf
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import feedparser
import datetime
import pandas as pd # <--- 引入 pandas 處理回測數據

# 1. 設定網頁標題
st.set_page_config(page_title="股票分析儀表板", layout="wide")
st.title("📈 股票分析儀表板 (含策略回測)")

# 2. 側邊欄參數
st.sidebar.header("📊 數據設定")
stock_id = st.sidebar.text_input("輸入股票代碼", value="2330.TW")

# 時間模式
time_mode = st.sidebar.radio("選擇時間模式", ["預設區間", "自訂日期"])
start_date = None
end_date = None
selected_period = None

if time_mode == "預設區間":
    selected_period = st.sidebar.selectbox("選擇時間範圍", ["3mo", "6mo", "1y", "2y", "5y", "max"], index=2)
else:
    default_start = datetime.date.today() - datetime.timedelta(days=365)
    start_date = st.sidebar.date_input("開始日期", default_start)
    end_date = st.sidebar.date_input("結束日期", datetime.date.today())

# 技術指標
st.sidebar.subheader("📈 圖表指標")
ma_days = st.sidebar.multiselect("顯示均線 (MA)", [5, 10, 20, 60, 120, 240], default=[5, 20])
show_bb = st.sidebar.checkbox("顯示布林通道", value=False)
show_vp = st.sidebar.checkbox("顯示籌碼密集區", value=True) 
show_gaps = st.sidebar.checkbox("顯示跳空缺口", value=True)

# --- 新增：回測設定 ---
st.sidebar.divider()
st.sidebar.subheader("💰 策略回測 (均線交叉)")
initial_capital = st.sidebar.number_input("初始本金 (TWD)", value=100000)
short_ma_window = st.sidebar.number_input("短期均線 (日)", value=5)
long_ma_window = st.sidebar.number_input("長期均線 (日)", value=20)
run_backtest_btn = st.sidebar.button("開始回測")

# 3. 抓取數據
def get_stock_data(ticker, mode, period=None, start=None, end=None):
    try:
        stock = yf.Ticker(ticker)
        if mode == "預設區間":
            hist = stock.history(period=period)
        else:
            hist = stock.history(start=start, end=end)
        return hist
    except Exception:
        return None

def get_google_news(query):
    try:
        rss_url = f"https://news.google.com/rss/search?q={query}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
        feed = feedparser.parse(rss_url)
        return feed.entries
    except:
        return []

# --- 新增：回測邏輯函數 ---
def run_backtest(df, short_window, long_window, initial_capital):
    # 複製一份資料以免影響原圖
    data = df.copy()
    
    # 1. 計算均線
    data['Short_MA'] = data['Close'].rolling(window=short_window).mean()
    data['Long_MA'] = data['Close'].rolling(window=long_window).mean()
    
    # 2. 產生訊號 (1: 黃金交叉/持倉, 0: 死亡交叉/空手)
    # 邏輯：短線 > 長線 = 持有 (1)
    data['Signal'] = 0
    data.loc[data['Short_MA'] > data['Long_MA'], 'Signal'] = 1
    
    # 計算買賣點 (diff=1 代表買進, diff=-1 代表賣出)
    data['Position'] = data['Signal'].diff()
    
    # 3. 模擬交易
    cash = initial_capital
    holdings = 0
    asset_history = [] # 記錄每天的總資產
    
    # 簡單模擬：全倉買進 / 全倉賣出
    for i in range(len(data)):
        price = data['Close'].iloc[i]
        signal = data['Signal'].iloc[i]
        position_change = data['Position'].iloc[i]
        
        # 如果是買點 (Position由0變1) 且手上沒股票
        if position_change == 1 and cash > 0:
            holdings = cash / price # 全倉買進
            cash = 0
            
        # 如果是賣點 (Position由1變0) 且手上有股票
        elif position_change == -1 and holdings > 0:
            cash = holdings * price # 全倉賣出
            holdings = 0
            
        # 計算當日總資產 (現金 + 股票市值)
        current_asset = cash + (holdings * price)
        asset_history.append(current_asset)
        
    data['Total_Asset'] = asset_history
    return data

# 5. 主程式
if stock_id:
    df = get_stock_data(stock_id, time_mode, period=selected_period, start=start_date, end=end_date)
    
    if df is not None and not df.empty:
        # --- A. 數據看板 ---
        col1, col2, col3, col4 = st.columns(4)
        current_price = df['Close'].iloc[-1]
        prev_price = df['Close'].iloc[-2]
        change = current_price - prev_price
        pct_change = (change / prev_price) * 100
        current_volume = df['Volume'].iloc[-1]

        col1.metric("當前股價", f"{current_price:.2f}", f"{change:.2f} ({pct_change:.2f}%)")
        col2.metric("最高價", f"{df['High'].max():.2f}")
        col3.metric("最低價", f"{df['Low'].min():.2f}")
        col4.metric("最新成交量", f"{current_volume:,}")

        # --- B. 畫走勢圖 ---
        st.subheader(f"📊 {stock_id} 走勢圖")
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.7, 0.3])
        fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name="K線"), row=1, col=1)

        colors = ['orange', 'blue', 'purple', 'black', 'green', 'red']
        for i, days in enumerate(ma_days):
            ma_name = f"MA{days}"
            df[ma_name] = df['Close'].rolling(window=days).mean()
            fig.add_trace(go.Scatter(x=df.index, y=df[ma_name], mode='lines', name=ma_name, line=dict(width=1.5, color=colors[i % len(colors)])), row=1, col=1)

        if show_bb:
            bb_period = 20
            std_dev = 2
            df['BB_Mid'] = df['Close'].rolling(window=bb_period).mean()
            df['BB_Std'] = df['Close'].rolling(window=bb_period).std()
            df['BB_Upper'] = df['BB_Mid'] + (std_dev * df['BB_Std'])
            df['BB_Lower'] = df['BB_Mid'] - (std_dev * df['BB_Std'])
            fig.add_trace(go.Scatter(x=df.index, y=df['BB_Lower'], line=dict(color='rgba(0,100,255,0.3)', width=1), mode='lines', showlegend=False), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['BB_Upper'], line=dict(color='rgba(0,100,255,0.3)', width=1), mode='lines', fill='tonexty', fillcolor='rgba(0,100,255,0.1)', name='布林通道'), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['BB_Mid'], line=dict(color='rgba(0,100,255,0.6)', width=1, dash='dash'), mode='lines', name='BB 中軌'), row=1, col=1)

        if show_vp:
            fig.add_trace(go.Histogram(
                y=df['Close'], x=df['Volume'], histfunc='sum', orientation='h', nbinsy=50, name="籌碼分佈",
                xaxis='x3', yaxis='y', marker=dict(color='rgba(31, 119, 180, 0.3)'), hoverinfo='none'
            ))
            max_vol = df['Volume'].max()
            fig.update_layout(xaxis3=dict(overlaying='x', side='top', showgrid=False, visible=False, range=[max_vol * 3, 0]))

        vol_colors = ['green' if row['Close'] >= row['Open'] else 'red' for index, row in df.iterrows()]
        fig.add_trace(go.Bar(x=df.index, y=df['Volume'], marker_color=vol_colors, name="成交量"), row=2, col=1)

        if show_gaps:
            gap_shapes = []
            for i in range(1, len(df)):
                curr_low, curr_high = df['Low'].iloc[i], df['High'].iloc[i]
                prev_high, prev_low = df['High'].iloc[i-1], df['Low'].iloc[i-1]
                curr_date, prev_date = df.index[i], df.index[i-1]
                if curr_low > prev_high:
                    gap_shapes.append(dict(type="rect", xref="x", yref="y", x0=prev_date, x1=curr_date, y0=prev_high, y1=curr_low, fillcolor="rgba(0,255,0,0.3)", line=dict(width=0)))
                elif curr_high < prev_low:
                    gap_shapes.append(dict(type="rect", xref="x", yref="y", x0=prev_date, x1=curr_date, y0=curr_high, y1=prev_low, fillcolor="rgba(255,0,0,0.3)", line=dict(width=0)))
            fig.update_layout(shapes=gap_shapes)

        fig.update_layout(xaxis_rangeslider_visible=False, height=600, showlegend=True, legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
        fig.update_xaxes(type='date', row=1, col=1)
        fig.update_xaxes(type='date', row=2, col=1)
        st.plotly_chart(fig, use_container_width=True)

        # --- C. 回測結果區塊 ---
        if run_backtest_btn:
            st.divider()
            st.subheader(f"💰 均線交叉回測結果 (MA{short_ma_window} vs MA{long_ma_window})")
            
            # 執行回測
            backtest_data = run_backtest(df, short_ma_window, long_ma_window, initial_capital)
            
            # 計算指標
            final_asset = backtest_data['Total_Asset'].iloc[-1]
            total_return = final_asset - initial_capital
            return_pct = (total_return / initial_capital) * 100
            
            # 顯示指標卡片
            b_col1, b_col2, b_col3 = st.columns(3)
            b_col1.metric("初始本金", f"{initial_capital:,}")
            b_col2.metric("最終資產", f"{int(final_asset):,}")
            b_col3.metric("總報酬率", f"{return_pct:.2f}%", delta=f"{total_return:,.0f}")
            
            # 畫資產曲線圖
            st.write("#### 資金成長曲線")
            fig_bt = go.Figure()
            # 畫資產線
            fig_bt.add_trace(go.Scatter(x=backtest_data.index, y=backtest_data['Total_Asset'], 
                                        mode='lines', name='總資產',
                                        line=dict(color='gold', width=2)))
            # 標示買點 (只標示有動作的點)
            buy_signals = backtest_data[backtest_data['Position'] == 1]
            sell_signals = backtest_data[backtest_data['Position'] == -1]
            
            fig_bt.add_trace(go.Scatter(x=buy_signals.index, y=buy_signals['Total_Asset'],
                                        mode='markers', name='買進',
                                        marker=dict(symbol='triangle-up', size=10, color='red')))
            
            fig_bt.add_trace(go.Scatter(x=sell_signals.index, y=sell_signals['Total_Asset'],
                                        mode='markers', name='賣出',
                                        marker=dict(symbol='triangle-down', size=10, color='green')))
            
            fig_bt.update_layout(height=400, hovermode="x unified")
            st.plotly_chart(fig_bt, use_container_width=True)

        # --- D. 新聞 ---
        st.divider()
        st.subheader(f"📰 {stock_id} 最新新聞")
        news_items = get_google_news(stock_id)
        if news_items:
            for item in news_items[:6]:
                with st.expander(item.title):
                    st.write(f"發布時間: {item.published}")
                    st.markdown(f"[👉 點擊閱讀全文]({item.link})")
        else:
            st.info("暫無新聞")

        # --- E. 表格 ---
        with st.expander("查看數據表格"):
            st.dataframe(df.sort_index(ascending=False))
