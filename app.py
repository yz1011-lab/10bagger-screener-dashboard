"""
10-Bagger 戰情儀表板 — Streamlit Cloud Edition v2
Features:
- Multi-market support (US/TW/JP/HK/EU)
- Clickable stock detail with score breakdown
- Real-time master analysis via NotebookLM (n8n webhook)
- Yahoo Finance recent news
- Bayesian probability updates with source citations
"""
import streamlit as st
import pandas as pd
import requests
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import json
import xml.etree.ElementTree as ET

# ============================================================================
# CONFIG
# ============================================================================
SUPABASE_URL = "https://oipvoeoxiiwcyhlbgedi.supabase.co"
ANON_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im9pcHZvZW94aWl3Y3lobGJnZWRpIiwi"
    "cm9sZSI6ImFub24iLCJpYXQiOjE3NzQyNzAzNzYsImV4cCI6MjA4OTg0NjM3Nn0."
    "tS1jud3TensTHdFKOb_ipXPq9-gzBgUDE51vlu9kjZw"
)
SCREENER_WEBHOOK = "https://shawnhuang.app.n8n.cloud/webhook/screener-agent"
MASTER_ANALYSIS_WEBHOOK = "https://shawnhuang.app.n8n.cloud/webhook/master-analysis"

st.set_page_config(
    page_title="10-Bagger 戰情儀表板",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ============================================================================
# SCORE WEIGHTS — mirrors the Merge & Rank code node in n8n
# ============================================================================
SCORE_WEIGHTS = {
    "relevance_score": {"label": "賽道相關性", "weight": 0.30, "desc": "Claude AI 判斷該股票與賽道主題的相關程度 (0-100)"},
    "gross_margin": {"label": "毛利率", "weight": 0.15, "desc": "毛利率越高代表定價能力與競爭優勢越強"},
    "revenue_growth": {"label": "營收成長率", "weight": 0.20, "desc": "年營收成長率，反映業務擴張速度"},
    "market_cap_score": {"label": "市值評分", "weight": 0.15, "desc": "市值越小(但不過小)越有爆發潛力"},
    "momentum_score": {"label": "動能評分", "weight": 0.20, "desc": "近期股價動能與趨勢強度"},
}

# ============================================================================
# MASTER OPINIONS DATA (from NotebookLM queries)
# ============================================================================
MASTERS = {
    "巴菲特": {
        "emoji": "🎩",
        "notebook_id": "ddbad0c0-54fd-46aa-abb9-f2fe37ecd581",
        "philosophy": (
            "能力圈、護城河、安全邊際、管理層品質、ROE。"
            "對小型成長股持保留態度，永遠選確定性成長而非快速成長。"
            "以合理價格買卓越公司，勝過以極佳價格買平庸公司。"
        ),
        "key_principles": [
            "能力圈：只投資能理解的企業",
            "經濟護城河：需持久競爭優勢",
            "安全邊際：買入價須顯著低於內在價值",
            "優秀管理層：誠實且理性分配資本",
            "穩健財務：高ROE、穩定現金流、低負債",
        ],
        "source": "NotebookLM — Warren Buffett 知識庫 (8 sources)",
    },
    "查理蒙格": {
        "emoji": "🧠",
        "notebook_id": "ca08d942-ac0f-4618-8371-ef8fe11f22e3",
        "philosophy": (
            "能力圈、護城河、安全邊際、反向思考、乘法為零效應。"
            "態度極度謹慎，對新興科技需「一直很聰明」的領域避而遠之。"
        ),
        "key_principles": [
            "能力圈：不投資超出理解範圍的領域",
            "反向思考：先問「這會如何讓我慘敗」",
            "乘法為零效應：任何關鍵環節失敗，整體歸零",
            "護城河 vs 創造性破壞：新興科技難建持久護城河",
            "安全邊際：常被過度炒作，缺乏穩定現金流支撐",
        ],
        "source": "NotebookLM — Charlie Munger 知識庫 (5 sources)",
    },
    "霍華馬克斯": {
        "emoji": "📐",
        "notebook_id": "501b59ab-aa22-4579-a02a-d87f13d18dec",
        "philosophy": (
            "第二層思考、風險評估、市場週期、逆向投資。"
            "真正的風險是永久虧損的可能性，不是波動性。"
        ),
        "key_principles": [
            "風險 ≠ 波動性：真正的風險是永久虧損的可能性",
            "市場週期必然輪迴：過度樂觀後必有修正",
            "第二層思考：若共識看好，問「已反映在價格中了嗎？」",
            "控制風險優先：最重要的事是控制風險",
            "逆向投資：在別人恐懼時貪婪",
        ],
        "source": "NotebookLM — Howard Marks 知識庫 (3 sources)",
    },
}

# ============================================================================
# DATA FETCHING
# ============================================================================
@st.cache_data(ttl=120)
def fetch_supabase(table, select="*", order=None, limit=None):
    url = f"{SUPABASE_URL}/rest/v1/{table}?select={select}"
    if order:
        url += f"&order={order}"
    if limit:
        url += f"&limit={limit}"
    headers = {"apikey": ANON_KEY, "Authorization": f"Bearer {ANON_KEY}"}
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        st.error(f"Supabase 讀取失敗: {e}")
        return []


def trigger_screener():
    try:
        resp = requests.post(
            SCREENER_WEBHOOK,
            json={"trigger": "manual", "timestamp": datetime.now().isoformat()},
            timeout=10,
        )
        return resp.status_code, resp.text[:200]
    except Exception as e:
        return 0, str(e)


@st.cache_data(ttl=600)
def fetch_yahoo_news(ticker, market="US"):
    """Fetch recent news from Yahoo Finance RSS."""
    # Build the Yahoo-compatible ticker symbol
    yahoo_ticker = ticker
    if market == "TW" and ".TW" not in ticker:
        yahoo_ticker = f"{ticker}.TW"
    elif market == "HK" and ".HK" not in ticker:
        yahoo_ticker = f"{ticker}.HK"
    elif market == "JP" and ".T" not in ticker:
        yahoo_ticker = f"{ticker}.T"

    url = f"https://finance.yahoo.com/rss/headline?s={yahoo_ticker}"
    try:
        resp = requests.get(url, timeout=10, headers={
            "User-Agent": "Mozilla/5.0 (compatible; 10BaggerBot/1.0)"
        })
        if resp.status_code != 200:
            return []
        root = ET.fromstring(resp.content)
        items = []
        for item in root.findall(".//item")[:8]:
            title = item.find("title")
            link = item.find("link")
            pub_date = item.find("pubDate")
            items.append({
                "title": title.text if title is not None else "",
                "link": link.text if link is not None else "",
                "date": pub_date.text[:16] if pub_date is not None else "",
            })
        return items
    except Exception:
        return []


def call_master_analysis(ticker, company_name, master_name, master_notebook_id):
    """Call n8n webhook for real-time NotebookLM master analysis."""
    try:
        resp = requests.post(
            MASTER_ANALYSIS_WEBHOOK,
            json={
                "ticker": ticker,
                "company_name": company_name,
                "master_name": master_name,
                "master_notebook_id": master_notebook_id,
                "timestamp": datetime.now().isoformat(),
            },
            timeout=60,
        )
        if resp.status_code == 200:
            data = resp.json()
            return data.get("analysis", resp.text[:2000])
        return f"⚠️ 分析服務回傳 HTTP {resp.status_code}"
    except requests.Timeout:
        return "⚠️ 分析請求逾時（60秒），請稍後再試"
    except Exception as e:
        return f"⚠️ 無法連線分析服務: {e}"


# ============================================================================
# URL HELPERS
# ============================================================================
def make_yahoo_url(ticker, market):
    if not ticker:
        return ""
    if market == "TW" and ".TW" not in ticker:
        return f"https://finance.yahoo.com/quote/{ticker}.TW"
    if market == "HK" and ".HK" not in ticker:
        return f"https://finance.yahoo.com/quote/{ticker}.HK"
    if market == "JP" and ".T" not in ticker:
        return f"https://finance.yahoo.com/quote/{ticker}.T"
    return f"https://finance.yahoo.com/quote/{ticker}"


def make_alphaspread_url(ticker, market):
    if not ticker:
        return ""
    t = ticker.replace(".TW", "").replace(".HK", "").replace(".T", "").lower()
    if market == "TW":
        return f"https://www.alphaspread.com/security/twse/{t}/summary"
    if market == "JP":
        return f"https://www.alphaspread.com/security/tse/{t}/summary"
    if market == "HK":
        return f"https://www.alphaspread.com/security/hkex/{t}/summary"
    return f"https://www.alphaspread.com/security/nasdaq/{t}/summary"


def make_sec_url(ticker):
    """Generate SEC EDGAR search URL for a ticker."""
    return f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&company={ticker}&type=10-K&dateb=&owner=include&count=5"


def make_finviz_url(ticker):
    return f"https://finviz.com/quote.ashx?t={ticker}"


def fmt_pct(val):
    if val is None or val == 0:
        return "-"
    return f"{val:.1f}%"


def fmt_cap(val):
    if not val:
        return "-"
    if val >= 1e9:
        return f"${val/1e9:.2f}B"
    return f"${val/1e6:.0f}M"


# ============================================================================
# SIDEBAR
# ============================================================================
with st.sidebar:
    st.title("🔍 10-Bagger 控制台")
    st.markdown("---")

    st.subheader("端到端測試")
    if st.button("🚀 觸發 Screener Agent", use_container_width=True):
        with st.spinner("觸發中..."):
            code, body = trigger_screener()
        if code == 200:
            st.success(f"✅ 觸發成功 (HTTP {code})")
        else:
            st.warning(f"⚠️ HTTP {code}: {body}")

    if st.button("🔄 重新整理資料", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    st.markdown("---")
    st.subheader("篩選標準")
    st.markdown(
        """
    - 🇺🇸 美國: 市值 < **$5B**
    - 🇪🇺🇯🇵🇹🇼 歐洲/日本/台灣: 市值 < **$1B**
    """
    )

    st.markdown("---")
    st.subheader("📡 資料來源")
    st.caption("Supabase (即時)")
    st.caption("Yahoo Finance (新聞)")
    st.caption("NotebookLM (大師看法)")
    st.caption(f"最後更新: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

# ============================================================================
# MAIN CONTENT
# ============================================================================
st.title("📊 10-Bagger 戰情儀表板")

# Fetch data
stocks_raw = fetch_supabase("stocks", order="composite_score.desc")
tracks_raw = fetch_supabase("tracks")
prob_log_raw = fetch_supabase("probability_log", order="created_at.desc")
config_raw = fetch_supabase("screener_config", limit=1)

if not stocks_raw:
    st.warning("⚠️ 尚無篩選結果。請點擊左側「觸發 Screener Agent」執行篩選。")
    st.stop()

df = pd.DataFrame(stocks_raw)
df_tracks = pd.DataFrame(tracks_raw) if tracks_raw else pd.DataFrame()
df_prob = pd.DataFrame(prob_log_raw) if prob_log_raw else pd.DataFrame()

# Show enabled markets from config
enabled_markets = []
if config_raw:
    enabled_markets = config_raw[0].get("enabled_markets", [])

# Ensure URL columns
if "yahoo_finance_url" not in df.columns:
    df["yahoo_finance_url"] = ""
if "alphaspread_url" not in df.columns:
    df["alphaspread_url"] = ""
for idx, row in df.iterrows():
    if not row.get("yahoo_finance_url"):
        df.at[idx, "yahoo_finance_url"] = make_yahoo_url(
            row.get("ticker", ""), row.get("market", "")
        )
    if not row.get("alphaspread_url"):
        df.at[idx, "alphaspread_url"] = make_alphaspread_url(
            row.get("ticker", ""), row.get("market", "")
        )

# ============================================================================
# METRICS ROW
# ============================================================================
col1, col2, col3, col4, col5 = st.columns(5)
with col1:
    st.metric("篩選總數", len(df))
with col2:
    markets = df["market"].nunique() if "market" in df.columns else 0
    st.metric("涵蓋市場", markets)
with col3:
    avg_score = df["composite_score"].mean() if "composite_score" in df.columns else 0
    st.metric("平均綜合分", f"{avg_score:.1f}")
with col4:
    us_count = len(df[df["market"] == "US"]) if "market" in df.columns else 0
    st.metric("🇺🇸 美股", us_count)
with col5:
    other_count = len(df[df["market"] != "US"]) if "market" in df.columns else 0
    st.metric("🌏 其他市場", other_count)

if enabled_markets:
    em_str = ", ".join(enabled_markets)
    if other_count == 0 and us_count > 0:
        st.info(
            f"ℹ️ 已設定啟用市場：**{em_str}**。目前僅有美股結果，"
            "因為 FMP API 的 `country` 參數對 TW/JP 市場支援有限。"
            "下次執行 Screener Agent 時將嘗試抓取多市場資料。"
        )
else:
    if other_count == 0:
        st.warning(
            "⚠️ `screener_config` 尚未設定 `enabled_markets`。"
            "請在 Supabase 中新增設定以啟用多市場篩選。"
        )

st.markdown("---")

# ============================================================================
# TABS
# ============================================================================
tab1, tab2, tab3, tab4 = st.tabs(
    ["📋 完整列表", "🏷️ 賽道分布", "📈 貝葉斯機率更新", "🏆 大師看法"]
)

# --- TAB 1: Full Stock List with Detail Panel ---
with tab1:
    st.subheader("篩選股票列表")

    fcol1, fcol2, fcol3 = st.columns(3)
    with fcol1:
        market_opts = sorted(df["market"].unique()) if "market" in df.columns else []
        market_filter = st.multiselect("市場", options=market_opts, default=market_opts)
    with fcol2:
        if "track_name" in df.columns:
            track_opts = sorted(df["track_name"].dropna().unique())
            track_filter = st.multiselect("賽道", options=track_opts, default=track_opts)
        else:
            track_filter = []
    with fcol3:
        max_score = (
            float(df["composite_score"].max())
            if "composite_score" in df.columns
            else 100.0
        )
        min_score = st.slider("最低綜合分", 0.0, max_score, 0.0)

    filtered = df.copy()
    if market_filter and "market" in filtered.columns:
        filtered = filtered[filtered["market"].isin(market_filter)]
    if track_filter and "track_name" in filtered.columns:
        filtered = filtered[filtered["track_name"].isin(track_filter)]
    if "composite_score" in filtered.columns:
        filtered = filtered[filtered["composite_score"] >= min_score]

    st.caption(f"顯示 {len(filtered)} / {len(df)} 檔股票")

    # Build display dataframe
    display_cols = []
    for _, row in filtered.iterrows():
        display_cols.append(
            {
                "Ticker": row.get("ticker", ""),
                "公司名稱": row.get("name", ""),
                "市場": row.get("market", ""),
                "賽道": row.get("track_name", "-"),
                "市值": fmt_cap(row.get("market_cap")),
                "毛利率": fmt_pct(row.get("gross_margin")),
                "營收成長": fmt_pct(row.get("revenue_growth")),
                "綜合分": f"{row.get('composite_score', 0):.1f}",
                "P(H)": f"{row.get('current_ph', 0):.1%}" if row.get("current_ph") else "-",
                "Yahoo Finance": row.get("yahoo_finance_url", ""),
                "Alphaspread": row.get("alphaspread_url", ""),
            }
        )

    display_df = pd.DataFrame(display_cols)
    st.dataframe(
        display_df,
        column_config={
            "Yahoo Finance": st.column_config.LinkColumn("Yahoo Finance", display_text="📈 查看"),
            "Alphaspread": st.column_config.LinkColumn("Alphaspread", display_text="📊 估值"),
        },
        hide_index=True,
        use_container_width=True,
        height=450,
    )

    # ---- STOCK DETAIL PANEL ----
    st.markdown("---")
    st.subheader("🔍 個股詳細分析")

    ticker_options = filtered["ticker"].tolist() if not filtered.empty else []
    if ticker_options:
        selected_ticker = st.selectbox(
            "選擇股票查看詳情",
            options=["-- 請選擇 --"] + ticker_options,
            index=0,
            key="stock_detail_select",
        )

        if selected_ticker != "-- 請選擇 --":
            stock_row = filtered[filtered["ticker"] == selected_ticker].iloc[0]
            stock_name = stock_row.get("name", selected_ticker)
            stock_market = stock_row.get("market", "US")

            st.markdown(f"### {selected_ticker} — {stock_name}")

            detail_tab1, detail_tab2, detail_tab3 = st.tabs(
                ["📊 綜合分數計算", "🏆 大師即時分析", "📰 近期新聞"]
            )

            # ---- Detail Tab 1: Score Breakdown ----
            with detail_tab1:
                st.markdown("#### 綜合分數計算方式")
                composite = stock_row.get("composite_score", 0)
                st.metric("綜合分數", f"{composite:.1f} / 100")

                st.markdown(
                    "綜合分數由以下五個維度加權計算，每個維度先標準化為 0-100 分後乘以權重："
                )

                # Show each component
                for key, info in SCORE_WEIGHTS.items():
                    raw_val = stock_row.get(key, None)
                    wcol1, wcol2, wcol3 = st.columns([3, 1, 4])
                    with wcol1:
                        st.markdown(f"**{info['label']}** (權重 {info['weight']:.0%})")
                    with wcol2:
                        if raw_val is not None and raw_val != 0:
                            if "margin" in key or "growth" in key:
                                st.markdown(f"`{raw_val:.1f}%`")
                            else:
                                st.markdown(f"`{raw_val:.1f}`")
                        else:
                            st.markdown("`-`")
                    with wcol3:
                        st.caption(info["desc"])

                # Visual bar chart
                weight_data = []
                for key, info in SCORE_WEIGHTS.items():
                    raw = stock_row.get(key)
                    # Estimate contribution (simplified)
                    contribution = (raw if raw and raw > 0 else 0) * info["weight"]
                    weight_data.append({"維度": info["label"], "加權貢獻": round(contribution, 1)})

                fig_weights = px.bar(
                    pd.DataFrame(weight_data),
                    x="維度", y="加權貢獻",
                    title=f"{selected_ticker} 各維度加權貢獻",
                    color="加權貢獻",
                    color_continuous_scale="Viridis",
                )
                fig_weights.update_layout(template="plotly_dark", plot_bgcolor="rgba(0,0,0,0)")
                st.plotly_chart(fig_weights, use_container_width=True)

                # AI reasoning
                reasoning = stock_row.get("reasoning", "")
                if reasoning:
                    st.markdown("#### 🤖 AI 篩選理由")
                    st.info(reasoning)

                # Quick links
                st.markdown("#### 🔗 研究連結")
                lcol1, lcol2, lcol3 = st.columns(3)
                with lcol1:
                    yahoo_url = make_yahoo_url(selected_ticker, stock_market)
                    st.markdown(f"[📈 Yahoo Finance]({yahoo_url})")
                with lcol2:
                    alpha_url = make_alphaspread_url(selected_ticker, stock_market)
                    st.markdown(f"[📊 Alphaspread 估值]({alpha_url})")
                with lcol3:
                    if stock_market == "US":
                        st.markdown(f"[📄 SEC EDGAR]({make_sec_url(selected_ticker)})")
                    else:
                        st.markdown(f"[📊 Finviz]({make_finviz_url(selected_ticker)})")

            # ---- Detail Tab 2: Master Analysis ----
            with detail_tab2:
                st.markdown("#### 選擇投資大師進行即時分析")
                st.caption(
                    "系統將合併公司分析資料與大師的 NotebookLM 知識庫，"
                    "使用最新 AI 模型生成大師視角的投資評估。"
                )

                master_names = list(MASTERS.keys())
                selected_master = st.selectbox(
                    "選擇大師",
                    options=master_names,
                    key=f"master_select_{selected_ticker}",
                )

                master_info = MASTERS[selected_master]

                # Show master philosophy
                with st.expander(f"{master_info['emoji']} {selected_master} 的投資哲學", expanded=False):
                    for principle in master_info["key_principles"]:
                        st.markdown(f"- {principle}")
                    st.caption(f"📚 {master_info['source']}")

                # Check for cached analysis in session state
                cache_key = f"analysis_{selected_ticker}_{selected_master}"

                if st.button(
                    f"🔮 以{selected_master}視角分析 {selected_ticker}",
                    use_container_width=True,
                    key=f"analyze_btn_{selected_ticker}_{selected_master}",
                ):
                    with st.spinner(f"正在以{selected_master}的視角分析 {stock_name}..."):
                        analysis = call_master_analysis(
                            selected_ticker,
                            stock_name,
                            selected_master,
                            master_info["notebook_id"],
                        )
                        st.session_state[cache_key] = analysis

                if cache_key in st.session_state:
                    st.markdown(f"### {master_info['emoji']} {selected_master}對 {selected_ticker} 的看法")
                    st.markdown(st.session_state[cache_key])
                    st.caption(
                        f"分析來源: NotebookLM {selected_master}知識庫 + 公司財務數據 | "
                        f"模型: Claude Sonnet 4 | "
                        f"生成時間: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
                    )
                else:
                    st.info("👆 點擊上方按鈕開始分析。系統將即時查詢 NotebookLM 知識庫生成大師看法。")

            # ---- Detail Tab 3: Recent News ----
            with detail_tab3:
                st.markdown(f"#### 📰 {selected_ticker} 近期新聞 (Yahoo Finance)")
                with st.spinner("載入新聞中..."):
                    news = fetch_yahoo_news(selected_ticker, stock_market)

                if news:
                    for item in news:
                        st.markdown(
                            f"- [{item['title']}]({item['link']}) "
                            f"<small style='color:gray'>({item['date']})</small>",
                            unsafe_allow_html=True,
                        )
                else:
                    st.info(
                        f"暫無 {selected_ticker} 的 Yahoo Finance 新聞。"
                        "可能是 RSS feed 暫時無法存取或該股票新聞較少。"
                    )

                # Additional news sources
                st.markdown("#### 🔗 更多新聞來源")
                ncol1, ncol2 = st.columns(2)
                with ncol1:
                    st.markdown(
                        f"[🔍 Google News 搜尋](https://news.google.com/search?q={selected_ticker}%20stock)"
                    )
                with ncol2:
                    st.markdown(
                        f"[📊 Seeking Alpha](https://seekingalpha.com/symbol/{selected_ticker})"
                    )
    else:
        st.info("尚無篩選結果可顯示。")

# --- TAB 2: Track Distribution ---
with tab2:
    st.subheader("賽道分布分析")

    if "track_name" in df.columns:
        track_counts = df["track_name"].value_counts().reset_index()
        track_counts.columns = ["賽道", "數量"]

        fig_bar = px.bar(
            track_counts,
            x="賽道", y="數量",
            title="各賽道篩選股票數量",
            color="數量",
            color_continuous_scale="Viridis",
        )
        fig_bar.update_layout(template="plotly_dark", plot_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig_bar, use_container_width=True)

        if "composite_score" in df.columns:
            track_stats = (
                df.groupby("track_name")
                .agg(
                    股票數=("ticker", "count"),
                    平均綜合分=("composite_score", "mean"),
                    最高綜合分=("composite_score", "max"),
                    平均市值M=("market_cap", lambda x: x.mean() / 1e6 if x.mean() else 0),
                )
                .round(1)
                .reset_index()
            )
            track_stats.columns = ["賽道", "股票數", "平均綜合分", "最高綜合分", "平均市值(M)"]
            st.dataframe(track_stats, hide_index=True, use_container_width=True)
    else:
        st.info("無賽道資訊")

# --- TAB 3: Bayesian Probability Updates with Sources ---
with tab3:
    st.subheader("📈 貝葉斯機率更新報告")

    if df_prob.empty:
        st.info("尚無貝葉斯更新記錄。需先執行 Macro Agent 分析。")
    else:
        st.markdown(
            f"共 **{len(df_prob)}** 筆更新記錄，"
            f"涵蓋 **{df_prob['stock_ticker'].nunique()}** 檔股票"
        )

        # Summary metrics
        pcol1, pcol2, pcol3, pcol4 = st.columns(4)
        with pcol1:
            surges = len(df_prob[df_prob.get("alert_type") == "surge"]) if "alert_type" in df_prob.columns else 0
            st.metric("🚀 機率飆升", surges)
        with pcol2:
            dangers = len(df_prob[df_prob.get("alert_type") == "danger"]) if "alert_type" in df_prob.columns else 0
            st.metric("⚠️ 風險警告", dangers)
        with pcol3:
            avg_conf = df_prob["confidence"].mean() if "confidence" in df_prob.columns else 0
            st.metric("平均信心度", f"{avg_conf:.0%}")
        with pcol4:
            avg_change = df_prob["change_amount"].mean() if "change_amount" in df_prob.columns else 0
            st.metric("平均變動", f"{avg_change:+.2f}")

        st.markdown("---")

        # Detail cards for each stock
        for _, row in df_prob.iterrows():
            ticker = row.get("stock_ticker", "")
            prior = row.get("prior_ph", 0)
            new_ph = row.get("new_ph", 0)
            change = row.get("change_amount", 0)
            confidence = row.get("confidence", 0)
            alert = row.get("alert_type", "")
            bull = row.get("bull_reasoning", "")
            bear = row.get("bear_counter_argument", "")
            judge = row.get("judge_ruling", "")
            evidence_count = row.get("evidence_count", 0)
            model_used = row.get("model_used", "")
            created_at = row.get("created_at", "")
            source_refs = row.get("source_references", [])
            event_type = row.get("event_type", "macro_analysis")

            # Color based on change direction
            if change > 0.1:
                icon = "🟢"
            elif change < -0.05:
                icon = "🔴"
            else:
                icon = "🟡"

            alert_badge = ""
            if alert == "surge":
                alert_badge = "🚀 SURGE"
            elif alert == "danger":
                alert_badge = "⚠️ DANGER"

            with st.container(border=True):
                hcol1, hcol2, hcol3, hcol4, hcol5 = st.columns([2, 1, 1, 1, 1])
                with hcol1:
                    st.markdown(f"### {icon} {ticker} {alert_badge}")
                with hcol2:
                    st.metric("Prior P(H)", f"{prior:.1%}")
                with hcol3:
                    st.metric("New P(H)", f"{new_ph:.1%}", delta=f"{change:+.2f}")
                with hcol4:
                    st.metric("信心度", f"{confidence:.0%}")
                with hcol5:
                    st.metric("變動幅度", f"{change:+.4f}")

                # WHY: Probability change explanation
                st.markdown("**📝 機率變動原因：**")
                if bull or bear or judge:
                    # Summary of WHY probability changed
                    direction = "上升" if change > 0 else "下降" if change < 0 else "持平"
                    st.markdown(
                        f"> 本次更新使 P(H) **{direction}** {abs(change):.4f}，"
                        f"基於 {evidence_count} 項證據的多空辯論後裁決。"
                    )

                    reasoning_col1, reasoning_col2 = st.columns(2)
                    with reasoning_col1:
                        if bull:
                            st.markdown("**🐂 多方論點：**")
                            st.markdown(f"> {bull}")
                    with reasoning_col2:
                        if bear:
                            st.markdown("**🐻 空方反駁：**")
                            st.markdown(f"> {bear}")
                    if judge:
                        st.markdown("**⚖️ 裁判裁決：**")
                        st.markdown(f"> {judge}")

                # SOURCE REFERENCES
                st.markdown("**📚 資料來源：**")

                # If source_references JSONB has data, show it
                if source_refs and isinstance(source_refs, list) and len(source_refs) > 0:
                    for ref in source_refs:
                        ref_type = ref.get("type", "未知")
                        ref_url = ref.get("url", "")
                        ref_desc = ref.get("description", "")
                        if ref_url:
                            st.markdown(f"- **{ref_type}**: [{ref_desc}]({ref_url})")
                        else:
                            st.markdown(f"- **{ref_type}**: {ref_desc}")
                else:
                    # Auto-generate source links based on available info
                    yahoo_url = make_yahoo_url(ticker, "US")
                    source_links = []

                    # Financial data source
                    source_links.append(
                        f"- **財務數據**: [Yahoo Finance — {ticker}]({yahoo_url})"
                    )

                    # SEC filings (for US stocks)
                    sec_url = make_sec_url(ticker)
                    source_links.append(
                        f"- **SEC 財報**: [EDGAR 10-K Filing]({sec_url})"
                    )

                    # News source
                    google_news = f"https://news.google.com/search?q={ticker}%20stock%20earnings"
                    source_links.append(
                        f"- **新聞**: [Google News — {ticker}]({google_news})"
                    )

                    for link in source_links:
                        st.markdown(link)

                # Metadata footer
                meta_parts = []
                if model_used:
                    meta_parts.append(f"模型: {model_used}")
                if evidence_count:
                    meta_parts.append(f"證據數: {evidence_count}")
                if event_type:
                    meta_parts.append(f"事件類型: {event_type}")
                if created_at:
                    ts = created_at[:19].replace("T", " ")
                    meta_parts.append(f"更新時間: {ts}")
                if meta_parts:
                    st.caption(" | ".join(meta_parts))

# --- TAB 4: Master Opinions (Overview) ---
with tab4:
    st.subheader("🏆 投資大師看法")
    st.markdown(
        "以下觀點來自 NotebookLM 知識庫中各投資大師的原始素材分析。"
        "如需針對特定股票的大師分析，請到「完整列表」選擇個股後進入「大師即時分析」。"
    )

    for master_name, master in MASTERS.items():
        with st.expander(
            f"{master['emoji']} {master_name}",
            expanded=True,
        ):
            st.markdown(f"**投資哲學：** {master['philosophy']}")
            st.markdown("---")
            st.markdown("**核心原則：**")
            for p in master["key_principles"]:
                st.markdown(f"- {p}")
            st.markdown("---")
            st.caption(f"📚 {master['source']}")

    st.markdown("---")
    st.markdown(
        "💡 **如何使用大師看法：** 在「完整列表」分頁選擇個股，進入「大師即時分析」子頁籤，"
        "選擇大師後點擊分析按鈕。系統會即時合併公司 NotebookLM 與大師 NotebookLM，"
        "搭配近期新聞產生專屬分析報告。"
    )

# ============================================================================
# FOOTER
# ============================================================================
st.markdown("---")
st.caption(
    "10-Bagger Agent System v2 | 戰情儀表板 | "
    "Powered by Supabase + n8n + NotebookLM + Yahoo Finance + Streamlit"
)
