"""
10-Bagger 戰情儀表板 — Streamlit Cloud Edition
Reads live data from Supabase: stocks, tracks, probability_log, master_opinions
"""
import streamlit as st
import pandas as pd
import requests
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime

# ============================================================================
# CONFIG
# ============================================================================
SUPABASE_URL = "https://oipvoeoxiiwcyhlbgedi.supabase.co"
ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im9pcHZvZW94aWl3Y3lobGJnZWRpIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzQyNzAzNzYsImV4cCI6MjA4OTg0NjM3Nn0.tS1jud3TensTHdFKOb_ipXPq9-gzBgUDE51vlu9kjZw"
SCREENER_WEBHOOK = "https://shawnhuang.app.n8n.cloud/webhook/screener-agent"

st.set_page_config(
    page_title="10-Bagger 戰情儀表板",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ============================================================================
# MASTER OPINIONS DATA (from NotebookLM queries)
# ============================================================================
MASTER_OPINIONS = [
    {
        "master_name": "巴菲特",
        "emoji": "🎩",
        "notebook_id": "ddbad0c0-54fd-46aa-abb9-f2fe37ecd581",
        "scope": "小型成長股投資",
        "question": "如何看待小型成長股？核心選股原則？",
        "opinion": (
            "對小型成長股持保留態度。在快速成長與確定性成長間永遠選後者，缺乏持久性護城河的早期快速成長並非理想投資。\n\n"
            "**核心選股原則：**\n"
            "1. **能力圈**：只投資能理解、商業模式簡單的企業\n"
            "2. **經濟護城河**：需持久競爭優勢（品牌、轉換成本、網絡效應）\n"
            "3. **安全邊際**：買入價須顯著低於內在價值\n"
            "4. **優秀管理層**：誠實且理性分配資本\n"
            "5. **穩健財務**：高ROE、穩定現金流、低負債\n"
            "6. **以合理價格買卓越公司**勝過以極佳價格買平庸公司"
        ),
        "philosophy_base": "能力圈、護城河、安全邊際、管理層品質、ROE",
        "source": "NotebookLM — Warren Buffett 知識庫 (8 sources)",
    },
    {
        "master_name": "查理蒙格",
        "emoji": "🧠",
        "notebook_id": "ca08d942-ac0f-4618-8371-ef8fe11f22e3",
        "scope": "新興科技小型股",
        "question": "對清潔能源、國防電子、AI 等新興科技小型股的看法？",
        "opinion": (
            "態度極度謹慎，會直接將多數排除在考慮之外。\n\n"
            "**核心思維模型：**\n"
            "1. **能力圈**：不投資超出理解範圍的領域，「不了解自己無知之處的人很危險」\n"
            "2. **護城河 vs 創造性破壞**：新興科技需「一直很聰明」，難建持久護城河\n"
            "3. **安全邊際**：常被過度炒作，缺乏穩定現金流作為估值支撐\n"
            "4. **反向思考**：不問「能賺多少」，先問「這會如何讓我慘敗」\n"
            "5. **乘法為零效應**：任何關鍵環節失敗（資金、技術、市場），整體歸零\n\n"
            "結論：除非具有絕對壟斷優勢與可預測的長遠未來，否則通常避而遠之。"
        ),
        "philosophy_base": "能力圈、護城河、安全邊際、反向思考、乘法為零效應",
        "source": "NotebookLM — Charlie Munger 知識庫 (5 sources)",
    },
    {
        "master_name": "霍華馬克斯",
        "emoji": "📐",
        "notebook_id": "501b59ab-aa22-4579-a02a-d87f13d18dec",
        "scope": "新興產業風險評估",
        "question": "如何評估新興產業小型股的風險與報酬？",
        "opinion": (
            "第二層思考的核心：當所有人都看好新興產業時，股價可能已反映過度樂觀預期。\n\n"
            "**關鍵原則：**\n"
            "1. **風險 ≠ 波動性**：真正的風險是永久虧損的可能性\n"
            "2. **市場週期必然輪迴**：過度樂觀後必有修正，週期從未消失\n"
            "3. **第二層思考**：若共識看好，要問「已經反映在價格中了嗎？」\n"
            "4. **控制風險優先**：最重要的事是控制風險，而非追求報酬\n"
            "5. **逆向投資**：在別人恐懼時貪婪，在別人貪婪時恐懼"
        ),
        "philosophy_base": "第二層思考、風險評估、市場週期、逆向投資",
        "source": "NotebookLM — Howard Marks 知識庫 (3 sources)",
    },
]

# ============================================================================
# DATA FETCHING
# ============================================================================
@st.cache_data(ttl=120)
def fetch_supabase(table, select="*", order=None):
    url = f"{SUPABASE_URL}/rest/v1/{table}?select={select}"
    if order:
        url += f"&order={order}"
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
            json={"trigger": "e2e_test", "timestamp": datetime.now().isoformat()},
            timeout=10,
        )
        return resp.status_code, resp.text[:200]
    except Exception as e:
        return 0, str(e)


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


def fmt_pct(val):
    """Format percent, showing '-' for 0 or None."""
    if val is None or val == 0:
        return "-"
    return f"{val:.1f}%"


def fmt_cap(val):
    """Format market cap."""
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

    # Show data source info
    st.subheader("📡 資料來源")
    st.caption("Supabase (即時)")
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

if not stocks_raw:
    st.warning("⚠️ 尚無篩選結果。請點擊左側「觸發 Screener Agent」執行篩選。")
    st.stop()

df = pd.DataFrame(stocks_raw)
df_tracks = pd.DataFrame(tracks_raw) if tracks_raw else pd.DataFrame()
df_prob = pd.DataFrame(prob_log_raw) if prob_log_raw else pd.DataFrame()

# Ensure URL columns + fill missing
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

if other_count == 0 and us_count > 0:
    st.info(
        "ℹ️ 目前僅有美股結果。原因：`screener_config` 資料表尚未設定 `enabled_markets`，"
        "且 FMP API 的 `country` 參數對 TW/JP 市場支援有限。"
        "建議在 Supabase `screener_config` 中新增設定行。"
    )

st.markdown("---")

# ============================================================================
# TABS
# ============================================================================
tab1, tab2, tab3, tab4 = st.tabs(
    ["📋 完整列表", "🏷️ 賽道分布", "📈 貝葉斯機率更新", "🏆 大師看法"]
)

# --- TAB 1: Full Stock List ---
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
            "Yahoo Finance": st.column_config.LinkColumn(
                "Yahoo Finance", display_text="📈 查看"
            ),
            "Alphaspread": st.column_config.LinkColumn(
                "Alphaspread", display_text="📊 估值"
            ),
        },
        hide_index=True,
        use_container_width=True,
        height=600,
    )

# --- TAB 2: Track Distribution ---
with tab2:
    st.subheader("賽道分布分析")

    if "track_name" in df.columns:
        track_counts = df["track_name"].value_counts().reset_index()
        track_counts.columns = ["賽道", "數量"]

        fig_bar = px.bar(
            track_counts,
            x="賽道",
            y="數量",
            title="各賽道篩選股票數量",
            color="數量",
            color_continuous_scale="Viridis",
        )
        fig_bar.update_layout(
            template="plotly_dark", plot_bgcolor="rgba(0,0,0,0)"
        )
        st.plotly_chart(fig_bar, use_container_width=True)

        if "composite_score" in df.columns:
            track_stats = (
                df.groupby("track_name")
                .agg(
                    股票數=("ticker", "count"),
                    平均綜合分=("composite_score", "mean"),
                    最高綜合分=("composite_score", "max"),
                    平均市值M=(
                        "market_cap",
                        lambda x: x.mean() / 1e6 if x.mean() else 0,
                    ),
                )
                .round(1)
                .reset_index()
            )
            track_stats.columns = [
                "賽道",
                "股票數",
                "平均綜合分",
                "最高綜合分",
                "平均市值(M)",
            ]
            st.dataframe(track_stats, hide_index=True, use_container_width=True)
    else:
        st.info("無賽道資訊")

# --- TAB 3: Bayesian Probability Updates ---
with tab3:
    st.subheader("📈 貝葉斯機率更新報告")

    if df_prob.empty:
        st.info("尚無貝葉斯更新記錄。需先執行 Macro Agent 分析。")
    else:
        st.markdown(
            f"共 **{len(df_prob)}** 筆更新記錄，涵蓋 **{df_prob['stock_ticker'].nunique()}** 檔股票"
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

            # Color based on change direction
            if change > 0.1:
                border_color = "#2ca02c"
                icon = "🟢"
            elif change < -0.05:
                border_color = "#d62728"
                icon = "🔴"
            else:
                border_color = "#ff9800"
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

                # Bull / Bear / Judge reasoning
                if bull or bear or judge:
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

# --- TAB 4: Master Opinions ---
with tab4:
    st.subheader("🏆 投資大師看法")
    st.markdown(
        "以下觀點來自 NotebookLM 知識庫中各投資大師的原始素材分析，"
        "針對本系統篩選的小型成長股類型提供哲學層面的評估。"
    )

    for master in MASTER_OPINIONS:
        with st.expander(
            f"{master['emoji']} {master['master_name']} — {master['scope']}",
            expanded=True,
        ):
            st.markdown(f"**提問：** {master['question']}")
            st.markdown("---")
            st.markdown(master["opinion"])
            st.markdown("---")

            mcol1, mcol2 = st.columns(2)
            with mcol1:
                st.markdown(f"**哲學基礎：** {master['philosophy_base']}")
            with mcol2:
                st.caption(f"📚 {master['source']}")

    st.markdown("---")
    st.markdown(
        "💡 **如何使用大師看法：** 在貝葉斯機率更新中，大師觀點可作為 "
        "Prior 校正的參考。若多位大師對某類型股票持保留態度，"
        "建議降低該類股的初始機率估計。"
    )

# ============================================================================
# FOOTER
# ============================================================================
st.markdown("---")
st.caption(
    "10-Bagger Agent System | 戰情儀表板 | "
    "Powered by Supabase + n8n + NotebookLM + Streamlit"
)
