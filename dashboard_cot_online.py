import os
from pathlib import Path
from datetime import datetime, timedelta
from io import BytesIO
import zipfile

import requests

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# ══════════════════════════════════════════════════════════════════════════════
# CONFIGURAÇÃO
# ══════════════════════════════════════════════════════════════════════════════
st.set_page_config(
    page_title="Relatório COT – CFTC",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Caminhos possíveis. Para publicar no Streamlit Cloud, deixe o CSV dentro da pasta dados_cot
# ou use variável de ambiente DATA_PATH.
POSSIVEIS_CAMINHOS = [
    os.getenv("DATA_PATH", ""),
    "dados_cot/cot_commodities_agro.csv",
    "dados_cot/cot_commodities_agro.xlsx",
    "cot_commodities_agro.csv",
    "cot_commodities_agro.xlsx",
    "dados_cot/cot_cbot_soja_milho.csv",
    "dados_cot/cot_cbot_soja_milho.xlsx",
    "cot_cbot_soja_milho.csv",
    "cot_cbot_soja_milho.xlsx",
    r"C:\Users\cotrirosa\Desktop\Lucas\Posição dos fundos\dados_cot\cot_commodities_agro.xlsx",
    r"C:\Users\cotrirosa\Desktop\Lucas\Posição dos fundos\dados_cot\cot_cbot_soja_milho.xlsx",
]

# Tickers contínuos do Yahoo Finance.
# Observação: alguns contratos são cotados em centavos; a função load_price_data converte quando necessário.
TICKERS_PRECO = {
    "Algodão": "CT=F",             # ICE Cotton No. 2 - centavos de US$/lb
    "Farelo de Soja": "ZM=F",      # CBOT Soybean Meal - US$/short ton
    "Milho": "ZC=F",              # CBOT Corn - centavos de US$/bushel
    "Óleo de Soja": "ZL=F",       # CBOT Soybean Oil - centavos de US$/lb
    "Soja": "ZS=F",               # CBOT Soybeans - centavos de US$/bushel
    "Trigo HRS (MGEX)": "MWE=F",   # MGEX Spring Wheat - normalmente centavos de US$/bushel
    "Trigo HRW (Kansas)": "KE=F",  # KC HRW Wheat - centavos de US$/bushel
}

UNIDADES_PRECO = {
    "Algodão": "US$/lb",
    "Farelo de Soja": "US$/short ton",
    "Milho": "US$/bushel",
    "Óleo de Soja": "US$/lb",
    "Soja": "US$/bushel",
    "Trigo HRS (MGEX)": "US$/bushel",
    "Trigo HRW (Kansas)": "US$/bushel",
}

# Commodities do Yahoo Finance que vêm em centavos e precisam ser divididas por 100.
CONVERTER_CENTAVOS = {
    "Algodão",
    "Milho",
    "Óleo de Soja",
    "Soja",
    "Trigo HRS (MGEX)",
    "Trigo HRW (Kansas)",
}

# Contratos principais aceitos por commodity.
# Serve para evitar que contratos "Mini" sejam somados/selecionados como se fossem o contrato cheio.
# Códigos observados nos arquivos Disaggregated Futures Only da CFTC.
CONTRATOS_PRINCIPAIS_CFTC = {
    "Algodão": {33661},
    "Farelo de Soja": {26603},
    "Milho": {2602},
    "Óleo de Soja": {7601},
    "Soja": {5602},
    "Trigo HRS (MGEX)": {1626},
    "Trigo HRW (Kansas)": {1612},
}


CATEGORIAS_ORDEM = [
    "Managed Money",
    "Non-Reportable",
    "Other Reportable",
    "Producer/Merchant",
    "Swap Dealers",
    "Total Reportable",
]

CATEGORIA_LABELS = {
    "Managed Money": "Managed Money",
    "Non-Reportable": "Non-Reportable",
    "Other Reportable": "Other Reportable",
    "Producer/Merchant": "Producers/Merchants",
    "Swap Dealers": "Swap Dealers",
    "Total Reportable": "Total Reportable",
}

# Cores ajustadas: Long verde, Short vermelho, Net azul escuro
PALETTE = {
    "long": "#1f9d55",
    "short": "#d64545",
    "net": "#0d1b2a",
    "net_pos": "#1f9d55",
    "net_neg": "#d64545",
    "price": "#d97706",
    "oi": "#64748b",
    "mm4": "#2e86c1",
    "mm12": "#8e44ad",
}

YEAR_COLORS = {
    "2021": "#94a3b8",
    "2022": "#64748b",
    "2023": "#1a3a5c",
    "2024": "#2980b9",
    "2025": "#85c1e9",
    "2026": "#f39c12",
}

CHART_LAYOUT = dict(
    paper_bgcolor="white",
    plot_bgcolor="#f8fafc",
    font=dict(family="Inter", size=12, color="#333"),
    margin=dict(t=70, l=55, r=55, b=82),
    # Legenda posicionada abaixo do gráfico para não ficar escondida pelos botões 6M/1A/3A/Tudo.
    legend=dict(orientation="h", yanchor="top", y=-0.18, xanchor="left", x=0, font=dict(size=11)),
    xaxis=dict(showgrid=True, gridcolor="#e8edf2", zeroline=False),
    yaxis=dict(showgrid=True, gridcolor="#e8edf2", zeroline=True, zerolinecolor="#ccd6df", zerolinewidth=1),
)

# ══════════════════════════════════════════════════════════════════════════════
# CSS
# ══════════════════════════════════════════════════════════════════════════════
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
.header-bar {
    background: linear-gradient(135deg, #0d1b2a 0%, #1b2d42 100%);
    padding: 18px 32px; border-radius: 10px; margin-bottom: 20px;
    display: flex; align-items: center; justify-content: space-between;
    border-left: 4px solid #2e86c1;
}
.header-title { color: #fff; font-size: 1.5rem; font-weight: 700; margin: 0; }
.header-sub { color: #aab7c4; font-size: 0.85rem; margin-top: 2px; }
.header-logo { color: #2e86c1; font-size: 1rem; font-weight: 700; letter-spacing: 1px; }
.kpi-card {
    background: #fff; border: 1px solid #e8edf2; border-radius: 10px; padding: 16px 18px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.06); text-align: center; border-top: 3px solid #2e86c1;
    min-height: 112px;
}
.kpi-label { color: #6b7a8d; font-size: 0.72rem; font-weight: 700; text-transform: uppercase; letter-spacing: .7px; margin-bottom: 5px; }
.kpi-value { color: #0d1b2a; font-size: 1.55rem; font-weight: 800; margin: 0; }
.kpi-delta { font-size: .78rem; font-weight: 600; margin-top: 4px; }
.kpi-up { color: #1f9d55; } .kpi-down { color: #d64545; } .kpi-neutral { color: #7f8c8d; }
.section-title { font-size: .95rem; font-weight: 700; color: #0d1b2a; border-left: 3px solid #2e86c1; padding-left: 10px; margin-bottom: 8px; }
.filter-bar { background: #f4f7fb; border-radius: 8px; padding: 12px 18px; border: 1px solid #dde3ec; margin-bottom: 16px; }
.insight-box { background: #fff; border: 1px solid #e8edf2; border-left: 4px solid #2e86c1; border-radius: 10px; padding: 16px 18px; box-shadow: 0 2px 8px rgba(0,0,0,.05); }
.insight-title { font-weight: 800; color: #0d1b2a; margin-bottom: 8px; }
.insight-text { color: #334155; font-size: .92rem; line-height: 1.55; }
.footer { text-align: center; color: #94a3b8; font-size: .72rem; padding: 20px 0 4px; border-top: 1px solid #e8edf2; margin-top: 28px; }
div[data-testid="stPlotlyChart"] > div { border-radius: 10px; box-shadow: 0 2px 8px rgba(0,0,0,.06); border: 1px solid #e8edf2; overflow: hidden; }
div[data-testid="stSelectbox"] > label, div[data-testid="stMultiSelect"] > label { font-weight: 700; color: #0d1b2a; font-size: .8rem; }
hr { border: none; border-top: 1px solid #e8edf2; margin: 20px 0; }
</style>
<script>
const meta = document.createElement('meta');
meta.name = 'google'; meta.content = 'notranslate';
document.head.appendChild(meta);
document.documentElement.setAttribute('translate', 'no');
document.documentElement.lang = 'pt-BR';
</script>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# FUNÇÕES
# ══════════════════════════════════════════════════════════════════════════════

def normalizar_colunas_cftc(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = (
        df.columns.astype(str)
        .str.strip()
        .str.replace(" ", "_", regex=False)
        .str.replace("-", "_", regex=False)
        .str.replace("/", "_", regex=False)
        .str.lower()
    )
    return df


def encontrar_coluna(df: pd.DataFrame, opcoes: list[str]) -> str:
    cols = set(df.columns)
    for col in [c.lower() for c in opcoes]:
        if col in cols:
            return col
    raise KeyError(f"Coluna não encontrada. Opções: {opcoes}")


def ler_arquivo_zip_cftc(conteudo_zip: bytes) -> pd.DataFrame:
    with zipfile.ZipFile(BytesIO(conteudo_zip)) as z:
        nomes = z.namelist()
        candidatos = [n for n in nomes if n.lower().endswith((".txt", ".csv"))]
        if not candidatos:
            candidatos = [n for n in nomes if n.lower().endswith((".xls", ".xlsx"))]
        if not candidatos:
            raise ValueError(f"ZIP da CFTC sem arquivo de dados. Arquivos: {nomes}")

        nome = candidatos[0]
        with z.open(nome) as f:
            if nome.lower().endswith((".txt", ".csv")):
                try:
                    df = pd.read_csv(f, low_memory=False, encoding="latin1")
                except Exception:
                    f.seek(0)
                    df = pd.read_csv(f, low_memory=False, encoding="utf-8")
            else:
                df = pd.read_excel(f)
    return normalizar_colunas_cftc(df)


def baixar_ano_cftc(ano: int) -> pd.DataFrame | None:
    # Fonte oficial: Historical Compressed · Disaggregated Futures Only · Text.
    # O arquivo Text evita depender de xlrd/openpyxl no Streamlit Cloud.
    urls = [
        f"https://www.cftc.gov/files/dea/history/fut_disagg_txt_{ano}.zip",
        f"https://www.cftc.gov/files/dea/history/fut_disagg_xls_{ano}.zip",
    ]
    headers = {
        "User-Agent": "Mozilla/5.0 (AgroBasis COT Dashboard; contato via agrobasis.com.br)",
        "Accept": "application/zip,application/octet-stream,*/*",
    }
    ultimo_erro = None
    for url in urls:
        for tentativa in range(3):
            try:
                r = requests.get(url, headers=headers, timeout=90)
                r.raise_for_status()
                df = ler_arquivo_zip_cftc(r.content)
                df["ano_origem"] = ano
                return df
            except Exception as e:
                ultimo_erro = e
                continue
    st.warning(f"Não consegui baixar {ano} da CFTC. Erro: {ultimo_erro}")
    return None


def padronizar_cot_online(bruto: pd.DataFrame) -> pd.DataFrame:
    df = bruto.copy()

    col_mercado = encontrar_coluna(df, ["market_and_exchange_names", "market_and_exchange_name"])
    col_data = encontrar_coluna(df, [
        "report_date_as_yyyy_mm_dd",
        "report_date_as_mm_dd_yyyy",
        "as_of_date_in_form_yymmdd",
        "as_of_date_form_yymmdd",
    ])
    col_codigo = encontrar_coluna(df, ["cftc_contract_market_code", "cftc_commodity_code"])
    col_oi = encontrar_coluna(df, ["open_interest_all"])

    df[col_codigo] = pd.to_numeric(df[col_codigo], errors="coerce")
    df = df.dropna(subset=[col_codigo]).copy()
    df["codigo_cftc"] = df[col_codigo].astype(int)

    codigo_para_commodity = {}
    for comm, codigos in CONTRATOS_PRINCIPAIS_CFTC.items():
        for codigo in codigos:
            codigo_para_commodity[int(codigo)] = comm

    df = df[df["codigo_cftc"].isin(codigo_para_commodity.keys())].copy()
    if df.empty:
        raise ValueError("A CFTC foi carregada, mas nenhum dos códigos principais de commodity foi encontrado.")

    df["commodity"] = df["codigo_cftc"].map(codigo_para_commodity)
    df["mercado_cftc"] = df[col_mercado].astype(str).str.strip()
    df["data"] = pd.to_datetime(df[col_data], errors="coerce")
    df = df.dropna(subset=["data"]).copy()
    df["open_interest"] = pd.to_numeric(df[col_oi], errors="coerce")

    categorias = {
        "Managed Money": {
            "long": ["m_money_positions_long_all"],
            "short": ["m_money_positions_short_all"],
            "spread": ["m_money_positions_spread_all"],
        },
        "Producer/Merchant": {
            "long": ["prod_merc_positions_long_all"],
            "short": ["prod_merc_positions_short_all"],
            "spread": [],
        },
        "Swap Dealers": {
            "long": ["swap_positions_long_all"],
            "short": ["swap__positions_short_all", "swap_positions_short_all"],
            "spread": ["swap__positions_spread_all", "swap_positions_spread_all"],
        },
        "Other Reportable": {
            "long": ["other_rept_positions_long_all"],
            "short": ["other_rept_positions_short_all"],
            "spread": ["other_rept_positions_spread_all", "other_rept_positions_spread_othr"],
        },
        "Non-Reportable": {
            "long": ["nonrept_positions_long_all"],
            "short": ["nonrept_positions_short_all"],
            "spread": [],
        },
        "Total Reportable": {
            "long": ["tot_rept_positions_long_all"],
            "short": ["tot_rept_positions_short_all"],
            "spread": [],
        },
    }

    partes = []
    for categoria, cols in categorias.items():
        col_long = encontrar_coluna(df, cols["long"])
        col_short = encontrar_coluna(df, cols["short"])

        temp = pd.DataFrame({
            "data": df["data"],
            "commodity": df["commodity"],
            "categoria": categoria,
            "mercado_cftc": df["mercado_cftc"],
            "codigo_cftc": df["codigo_cftc"],
            "open_interest": df["open_interest"],
            "long": pd.to_numeric(df[col_long], errors="coerce"),
            "short": pd.to_numeric(df[col_short], errors="coerce"),
        })

        if cols["spread"]:
            try:
                col_spread = encontrar_coluna(df, cols["spread"])
                temp["spread"] = pd.to_numeric(df[col_spread], errors="coerce")
            except KeyError:
                temp["spread"] = 0
        else:
            temp["spread"] = 0

        partes.append(temp)

    final = pd.concat(partes, ignore_index=True)
    final = final.dropna(subset=["data", "commodity", "categoria"]).copy()
    final["net"] = final["long"] - final["short"]

    # Evita duplicidade por data/commodity/categoria, mantendo o contrato principal de maior OI.
    final = final.sort_values(["commodity", "categoria", "data", "open_interest"])
    final = final.drop_duplicates(subset=["commodity", "categoria", "data"], keep="last")

    final = final.sort_values(["commodity", "categoria", "data"])
    final["variacao_semanal_net"] = final.groupby(["commodity", "categoria"])["net"].diff()
    final["media_4s_net"] = final.groupby(["commodity", "categoria"])["net"].transform(lambda x: x.rolling(4).mean())
    final["media_12s_net"] = final.groupby(["commodity", "categoria"])["net"].transform(lambda x: x.rolling(12).mean())
    final["ano"] = final["data"].dt.year
    final["mes"] = final["data"].dt.month
    final["semana_ano"] = final["data"].dt.isocalendar().week.astype(int)
    return final


@st.cache_data(ttl=21600, show_spinner=False)
def load_data_online(ano_inicial: int = 2010) -> pd.DataFrame:
    ano_final = datetime.now().year
    todos = []
    erros = []
    for ano in range(ano_inicial, ano_final + 1):
        df_ano = baixar_ano_cftc(ano)
        if df_ano is not None and not df_ano.empty:
            todos.append(df_ano)
        else:
            erros.append(str(ano))

    if not todos:
        raise RuntimeError("Nenhum arquivo da CFTC foi baixado. Verifique conexão ou disponibilidade da CFTC.")

    bruto = pd.concat(todos, ignore_index=True)
    tratado = padronizar_cot_online(bruto)
    if tratado.empty:
        raise RuntimeError("Os arquivos foram baixados, mas a base tratada ficou vazia.")
    return tratado

@st.cache_data(ttl=900, show_spinner=False)
def load_price_data(commodity: str, start_date, end_date) -> pd.DataFrame:
    ticker = TICKERS_PRECO.get(commodity)
    if not ticker:
        return pd.DataFrame()
    try:
        import yfinance as yf
        px = yf.download(ticker, start=start_date, end=end_date + timedelta(days=5), progress=False, auto_adjust=False)
        if px.empty:
            return pd.DataFrame()
        px = px.reset_index()
        date_col = "Date" if "Date" in px.columns else px.columns[0]
        close_col = "Close" if "Close" in px.columns else "Adj Close"
        out = px[[date_col, close_col]].copy()
        out.columns = ["data_preco", "preco"]
        out["data_preco"] = pd.to_datetime(out["data_preco"]).dt.tz_localize(None)
        out["preco"] = pd.to_numeric(out["preco"], errors="coerce")
        # Alguns contratos do Yahoo Finance vêm em centavos.
        # Convertemos para dólar por unidade para ficar mais intuitivo no dashboard.
        if commodity in CONVERTER_CENTAVOS:
            out["preco"] = out["preco"] / 100
        return out.dropna()
    except Exception:
        return pd.DataFrame()

def adicionar_marca_agua(fig, texto="AgroBasis"):
    fig.add_annotation(
        text=texto,
        xref="paper", yref="paper", x=0.5, y=0.5,
        showarrow=False,
        font=dict(size=48, color="rgba(13, 27, 42, 0.06)"),
        textangle=-22,
        xanchor="center", yanchor="middle",
    )
    return fig

def add_range_buttons(fig):
    fig.update_xaxes(
        rangeselector=dict(
            buttons=[
                dict(count=6, label="6M", step="month", stepmode="backward"),
                dict(count=1, label="1A", step="year", stepmode="backward"),
                dict(count=3, label="3A", step="year", stepmode="backward"),
                dict(step="all", label="Tudo"),
            ],
            bgcolor="#f4f7fb", activecolor="#2e86c1", font=dict(size=11),
        ),
        rangeslider=dict(visible=False),
    )

def fmt_mil(v, sinal=False):
    if pd.isna(v):
        return "—"
    prefix = "+" if sinal and v > 0 else ""
    return f"{prefix}{v/1000:,.1f} mil".replace(",", "X").replace(".", ",").replace("X", ".")

def fmt_pct(v):
    if pd.isna(v):
        return "—"
    return f"{v:.1f}%".replace(".", ",")

def kpi_card(col, label, value, delta=None, suffix="", color_top="#2e86c1"):
    delta_html = ""
    if delta is not None and not pd.isna(delta):
        cls = "kpi-up" if delta > 0 else ("kpi-down" if delta < 0 else "kpi-neutral")
        sign = "▲" if delta > 0 else ("▼" if delta < 0 else "—")
        delta_html = f'<p class="kpi-delta {cls}">{sign} {fmt_mil(abs(delta))} na semana</p>'
    col.markdown(f"""
    <div class="kpi-card" style="border-top-color:{color_top}">
        <div class="kpi-label">{label}</div>
        <p class="kpi-value">{value}{suffix}</p>
        {delta_html}
    </div>
    """, unsafe_allow_html=True)

def calcular_indicadores(df):
    latest = df.iloc[-1]
    prev = df.iloc[-2] if len(df) >= 2 else latest
    net = latest["net"]
    serie_net = df["net"].dropna()
    percentil = (serie_net.rank(pct=True).iloc[-1] * 100) if len(serie_net) else np.nan
    media = serie_net.mean()
    desvio = serie_net.std()
    zscore = (net - media) / desvio if desvio and not pd.isna(desvio) else np.nan
    oi = latest.get("open_interest", np.nan)
    net_oi = (net / oi * 100) if not pd.isna(oi) and oi != 0 else np.nan
    return latest, prev, percentil, zscore, oi, net_oi

def gerar_insights(df, commodity, categoria, percentil, zscore, net_oi):
    latest = df.iloc[-1]
    ult4 = df.tail(4)["variacao_semanal_net"].sum()
    ult12 = df.tail(12)["variacao_semanal_net"].sum()
    direcao = "compraram" if ult4 > 0 else "venderam"
    extremo = "neutro"
    if percentil >= 90:
        extremo = "entre os níveis historicamente mais comprados"
    elif percentil <= 10:
        extremo = "entre os níveis historicamente mais vendidos"
    elif zscore >= 1.5:
        extremo = "acima da média histórica"
    elif zscore <= -1.5:
        extremo = "abaixo da média histórica"

    texto_net_oi = ""
    if not pd.isna(net_oi):
        texto_net_oi = f" A posição líquida equivale a <b>{fmt_pct(net_oi)}</b> do open interest."

    return f"""
    <div class="insight-box">
      <div class="insight-title">Leitura automática · {commodity} · {CATEGORIA_LABELS.get(categoria, categoria)}</div>
      <div class="insight-text">
        Na última leitura, a posição líquida está em <b>{fmt_mil(latest['net'], sinal=True)}</b> contratos.
        Nas últimas 4 semanas, os participantes <b>{direcao}</b> aproximadamente <b>{fmt_mil(abs(ult4))}</b> contratos líquidos.
        Em 12 semanas, a mudança acumulada foi de <b>{fmt_mil(ult12, sinal=True)}</b>.
        O posicionamento atual está no <b>percentil {fmt_pct(percentil)}</b> da série e o z-score é <b>{zscore:.2f}</b>, indicando um nível <b>{extremo}</b>.{texto_net_oi}
      </div>
    </div>
    """

# ══════════════════════════════════════════════════════════════════════════════
# CARREGAMENTO
# ══════════════════════════════════════════════════════════════════════════════
with st.spinner("Carregando dados oficiais da CFTC... Na primeira abertura pode demorar um pouco."):
    try:
        df_all = load_data_online(ano_inicial=2010)
    except Exception as e:
        st.error(f"Não foi possível carregar os dados da CFTC: {e}")
        st.stop()

DATA_PATH = "CFTC online · Disaggregated Futures Only"

# ══════════════════════════════════════════════════════════════════════════════
# HEADER
# ══════════════════════════════════════════════════════════════════════════════
st.markdown("""
<div class="header-bar">
  <div>
    <p class="header-title">📊 Relatório de Posições (COT) – CFTC</p>
    <p class="header-sub">Commitments of Traders · Grãos, oleaginosas, algodão e trigo · Dados semanais</p>
  </div>
  <div class="header-logo">AGROBASIS · FLUXO DOS FUNDOS</div>
</div>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# FILTROS
# ══════════════════════════════════════════════════════════════════════════════
st.markdown('<div class="filter-bar" translate="no">', unsafe_allow_html=True)
fc1, fc2, fc3, fc4 = st.columns([1.5, 2.5, 2.5, 1.2])

with fc1:
    commodities_disp = sorted(df_all["commodity"].dropna().unique())
    idx_soja = commodities_disp.index("Soja") if "Soja" in commodities_disp else 0
    commodity = st.selectbox("🌱 Commodity", commodities_disp, index=idx_soja)
with fc2:
    cats_disp = [c for c in CATEGORIAS_ORDEM if c in df_all["categoria"].unique()]
    categoria = st.selectbox("📂 Categoria", cats_disp, format_func=lambda x: CATEGORIA_LABELS.get(x, x))
with fc3:
    anos_disp = sorted(df_all["ano"].dropna().astype(int).unique(), reverse=True)
    default_anos = [a for a in [2026, 2025, 2024, 2023] if a in anos_disp]
    anos_sel = st.multiselect("📅 Anos comparativo", anos_disp, default=default_anos)
with fc4:
    buscar_preco = st.toggle("Preço futuro", value=True)

st.markdown("</div>", unsafe_allow_html=True)

df = df_all[(df_all["commodity"] == commodity) & (df_all["categoria"] == categoria)].copy().sort_values("data")
if df.empty:
    st.warning("Sem dados para os filtros selecionados.")
    st.stop()

latest, prev, percentil, zscore, oi, net_oi = calcular_indicadores(df)

# Preço CBOT opcional
price_df = pd.DataFrame()
df_preco = df.copy()
if buscar_preco:
    price_df = load_price_data(commodity, df["data"].min() - timedelta(days=10), df["data"].max() + timedelta(days=3))
    if not price_df.empty:
        df_preco = pd.merge_asof(
            df.sort_values("data"),
            price_df.sort_values("data_preco"),
            left_on="data",
            right_on="data_preco",
            direction="nearest",
            tolerance=pd.Timedelta("5D"),
        )

# ══════════════════════════════════════════════════════════════════════════════
# KPIs
# ══════════════════════════════════════════════════════════════════════════════
k1, k2, k3, k4, k5, k6, k7 = st.columns(7)
kpi_card(k1, "Long", fmt_mil(latest["long"]), latest["long"] - prev["long"], color_top=PALETTE["long"])
kpi_card(k2, "Short", fmt_mil(latest["short"]), latest["short"] - prev["short"], color_top=PALETTE["short"])
kpi_card(k3, "Net", fmt_mil(latest["net"], sinal=True), latest["net"] - prev["net"], color_top=PALETTE["net"])
kpi_card(k4, "Percentil histórico", fmt_pct(percentil), None, color_top="#d97706")
kpi_card(k5, "Z-Score", "—" if pd.isna(zscore) else f"{zscore:.2f}", None, color_top="#8e44ad")
kpi_card(k6, "Open Interest", fmt_mil(oi), None, color_top=PALETTE["oi"])
kpi_card(k7, "Net / OI", fmt_pct(net_oi), None, color_top="#0f766e")

st.markdown("<br>", unsafe_allow_html=True)
st.markdown(gerar_insights(df, commodity, categoria, percentil, zscore, net_oi), unsafe_allow_html=True)
st.markdown("<br>", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# TABS
# ══════════════════════════════════════════════════════════════════════════════
tab1, tab2, tab3 = st.tabs(["📈 Gráficos", "🔥 Heatmap", "📋 Tabela de Dados"])

with tab1:
    col_a, col_b = st.columns(2, gap="medium")

    with col_a:
        st.markdown('<p class="section-title">Posição dos fundos · Long, Short e Net</p>', unsafe_allow_html=True)
        df_plot = df[df["ano"] >= df["ano"].max() - 3].copy()
        fig1 = go.Figure()
        fig1.add_trace(go.Bar(x=df_plot["data"], y=df_plot["long"], name="Long", marker_color=PALETTE["long"], opacity=.85))
        fig1.add_trace(go.Bar(x=df_plot["data"], y=-df_plot["short"], name="Short", marker_color=PALETTE["short"], opacity=.75))
        fig1.add_trace(go.Scatter(x=df_plot["data"], y=df_plot["net"], name="Net", mode="lines", line=dict(color=PALETTE["net"], width=2.5)))
        fig1.add_hline(y=0, line_color="#ccd6df", line_width=1)
        fig1.update_layout(**CHART_LAYOUT, barmode="overlay", yaxis_title="Contratos", hovermode="x unified", height=390)
        fig1.update_yaxes(tickformat=".2s")
        add_range_buttons(fig1)
        adicionar_marca_agua(fig1)
        st.plotly_chart(fig1, use_container_width=True, config={"displayModeBar": False})

    with col_b:
        st.markdown('<p class="section-title">Net x Preço futuro</p>', unsafe_allow_html=True)
        figp = go.Figure()
        figp.add_trace(go.Scatter(x=df_preco["data"], y=df_preco["net"], name="Net", mode="lines", line=dict(color=PALETTE["net"], width=2.2), yaxis="y1"))
        if "preco" in df_preco.columns and df_preco["preco"].notna().any():
            figp.add_trace(go.Scatter(x=df_preco["data"], y=df_preco["preco"], name=f"Preço futuro ({UNIDADES_PRECO.get(commodity, 'US$')})", mode="lines", line=dict(color=PALETTE["price"], width=2), yaxis="y2", hovertemplate="%{y:.2f}<extra></extra>"))
        else:
            figp.add_annotation(text="Preço não carregado. Instale yfinance ou desative/ative o botão Preço futuro.", xref="paper", yref="paper", x=.5, y=.92, showarrow=False, font=dict(color="#64748b", size=12))
        figp.update_layout(**CHART_LAYOUT, hovermode="x unified", height=390)
        figp.update_layout(
            yaxis=dict(
                title="Net · Contratos",
                tickformat=".2s",
                showgrid=True,
                gridcolor="#e8edf2",
                zeroline=True,
                zerolinecolor="#ccd6df",
                zerolinewidth=1,
            ),
            yaxis2=dict(
                title=f"Preço futuro ({UNIDADES_PRECO.get(commodity, 'US$')})",
                overlaying="y",
                side="right",
                showgrid=False,
                tickprefix="US$ ",
                tickformat=".2f",
            ),
        )
        add_range_buttons(figp)
        adicionar_marca_agua(figp)
        st.plotly_chart(figp, use_container_width=True, config={"displayModeBar": False})

    st.markdown("<hr>", unsafe_allow_html=True)
    col_c, col_d = st.columns(2, gap="medium")

    with col_c:
        st.markdown('<p class="section-title">Net histórico com médias móveis</p>', unsafe_allow_html=True)
        fig3 = go.Figure()
        fig3.add_trace(go.Scatter(x=df["data"], y=df["net"], name="Net", mode="lines", line=dict(color=PALETTE["net"], width=1.7), opacity=.75))
        fig3.add_trace(go.Scatter(x=df["data"], y=df["media_4s_net"], name="Média 4s", mode="lines", line=dict(color=PALETTE["mm4"], width=2, dash="dot")))
        fig3.add_trace(go.Scatter(x=df["data"], y=df["media_12s_net"], name="Média 12s", mode="lines", line=dict(color=PALETTE["mm12"], width=2, dash="dash")))
        fig3.add_hline(y=0, line_color="#ccd6df", line_width=1)
        fig3.update_layout(**CHART_LAYOUT, yaxis_title="Contratos", hovermode="x unified", height=380)
        fig3.update_yaxes(tickformat=".2s")
        add_range_buttons(fig3)
        adicionar_marca_agua(fig3)
        st.plotly_chart(fig3, use_container_width=True, config={"displayModeBar": False})

    with col_d:
        st.markdown('<p class="section-title">Variação semanal da posição líquida</p>', unsafe_allow_html=True)
        df_var = df.dropna(subset=["variacao_semanal_net"]).copy()
        df_var = df_var[df_var["ano"] >= df_var["ano"].max() - 2]
        colors_var = [PALETTE["net_pos"] if v >= 0 else PALETTE["net_neg"] for v in df_var["variacao_semanal_net"]]
        fig2 = go.Figure()
        fig2.add_trace(go.Bar(x=df_var["data"], y=df_var["variacao_semanal_net"], name="Var. semanal", marker_color=colors_var, opacity=.9))
        fig2.add_hline(y=0, line_color="#ccd6df", line_width=1)
        fig2.update_layout(**CHART_LAYOUT, yaxis_title="Contratos", hovermode="x unified", height=380)
        fig2.update_yaxes(tickformat=".2s")
        add_range_buttons(fig2)
        adicionar_marca_agua(fig2)
        st.plotly_chart(fig2, use_container_width=True, config={"displayModeBar": False})

    st.markdown("<hr>", unsafe_allow_html=True)
    col_e, col_f = st.columns(2, gap="medium")
    anos_plot = [a for a in anos_sel if a in df["ano"].unique()]
    if not anos_plot:
        anos_plot = [int(df["ano"].max())]

    with col_e:
        st.markdown('<p class="section-title">Comparativo anual · Net por semana do ano</p>', unsafe_allow_html=True)
        fig4 = go.Figure()
        for ano in sorted(anos_plot):
            sub = df[df["ano"] == ano]
            fig4.add_trace(go.Scatter(x=sub["semana_ano"], y=sub["net"], name=str(ano), mode="lines", line=dict(color=YEAR_COLORS.get(str(ano), "#999"), width=2.6 if ano == max(anos_plot) else 1.7)))
        fig4.add_hline(y=0, line_color="#ccd6df", line_width=1)
        fig4.update_layout(**CHART_LAYOUT, xaxis_title="Semana do ano", yaxis_title="Contratos", hovermode="x unified", height=370)
        fig4.update_yaxes(tickformat=".2s")
        fig4.update_xaxes(range=[1, 52], dtick=4)
        adicionar_marca_agua(fig4)
        st.plotly_chart(fig4, use_container_width=True, config={"displayModeBar": False})

    with col_f:
        st.markdown('<p class="section-title">Open Interest e Net / OI</p>', unsafe_allow_html=True)
        fig_oi = go.Figure()
        if df["open_interest"].notna().any():
            df_oi = df.copy()
            df_oi["net_oi"] = df_oi["net"] / df_oi["open_interest"] * 100
            fig_oi.add_trace(go.Scatter(x=df_oi["data"], y=df_oi["open_interest"], name="Open Interest", mode="lines", line=dict(color=PALETTE["oi"], width=2), yaxis="y1"))
            fig_oi.add_trace(go.Scatter(x=df_oi["data"], y=df_oi["net_oi"], name="Net / OI", mode="lines", line=dict(color="#0f766e", width=2), yaxis="y2"))
        else:
            fig_oi.add_annotation(text="Open Interest não está na base atual. Inclua a coluna open_interest no coletor para habilitar este gráfico.", xref="paper", yref="paper", x=.5, y=.5, showarrow=False, font=dict(color="#64748b", size=13), align="center")
        fig_oi.update_layout(**CHART_LAYOUT, hovermode="x unified", height=370)
        fig_oi.update_layout(
            yaxis2=dict(title="Net / OI (%)", overlaying="y", side="right", showgrid=False)
        )
        fig_oi.update_yaxes(title_text="Open Interest", tickformat=".2s", showgrid=True, gridcolor="#e8edf2")
        add_range_buttons(fig_oi)
        adicionar_marca_agua(fig_oi)
        st.plotly_chart(fig_oi, use_container_width=True, config={"displayModeBar": False})

with tab2:
    st.markdown('<p class="section-title">Heatmap sazonal · Variação média mensal da posição líquida</p>', unsafe_allow_html=True)
    heat = df.dropna(subset=["variacao_semanal_net"]).copy()
    heat["var_mensal_media"] = heat["variacao_semanal_net"]
    pivot = heat.pivot_table(index="ano", columns="mes", values="var_mensal_media", aggfunc="sum")
    pivot = pivot.reindex(columns=list(range(1, 13)))
    meses = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]
    fig_heat = go.Figure(data=go.Heatmap(
        z=pivot.values,
        x=meses,
        y=pivot.index.astype(str),
        colorscale="RdYlGn",
        zmid=0,
        colorbar=dict(title="Contratos"),
        hovertemplate="Ano: %{y}<br>Mês: %{x}<br>Variação: %{z:,.0f} contratos<extra></extra>",
    ))
    fig_heat.update_layout(**CHART_LAYOUT, height=520, xaxis_title="Mês", yaxis_title="Ano")
    adicionar_marca_agua(fig_heat)
    st.plotly_chart(fig_heat, use_container_width=True, config={"displayModeBar": False})

    st.markdown('<p class="section-title">Média histórica por mês</p>', unsafe_allow_html=True)
    mensal = heat.groupby("mes", as_index=False)["variacao_semanal_net"].sum()
    mensal_media = heat.groupby(["ano", "mes"], as_index=False)["variacao_semanal_net"].sum().groupby("mes", as_index=False)["variacao_semanal_net"].mean()
    colors_m = [PALETTE["net_pos"] if v >= 0 else PALETTE["net_neg"] for v in mensal_media["variacao_semanal_net"]]
    fig_m = go.Figure(go.Bar(x=[meses[m-1] for m in mensal_media["mes"]], y=mensal_media["variacao_semanal_net"], marker_color=colors_m, name="Média mensal"))
    fig_m.add_hline(y=0, line_color="#ccd6df", line_width=1)
    fig_m.update_layout(**CHART_LAYOUT, height=340, yaxis_title="Contratos")
    adicionar_marca_agua(fig_m)
    st.plotly_chart(fig_m, use_container_width=True, config={"displayModeBar": False})

with tab3:
    st.markdown(f'<p class="section-title">Dados históricos · {commodity} · {CATEGORIA_LABELS.get(categoria, categoria)}</p>', unsafe_allow_html=True)
    colunas = ["data", "mercado_cftc", "codigo_cftc", "long", "short", "spread", "net", "variacao_semanal_net", "media_4s_net", "media_12s_net", "open_interest"]
    df_table = df[[c for c in colunas if c in df.columns]].copy().sort_values("data", ascending=False)
    df_table["data"] = df_table["data"].dt.strftime("%d/%m/%Y")
    renomear = {
        "data": "Data", "mercado_cftc": "Mercado CFTC", "codigo_cftc": "Código CFTC", "long": "Long", "short": "Short", "spread": "Spread", "net": "Net",
        "variacao_semanal_net": "Var. Semanal Net", "media_4s_net": "Média 4s Net", "media_12s_net": "Média 12s Net",
        "open_interest": "Open Interest",
    }
    df_table = df_table.rename(columns=renomear)

    def highlight_net(val):
        try:
            if val > 0:
                return "color: #1f9d55; font-weight:700"
            if val < 0:
                return "color: #d64545; font-weight:700"
        except Exception:
            return ""
        return ""

    styled = df_table.style.applymap(highlight_net, subset=[c for c in ["Net", "Var. Semanal Net"] if c in df_table.columns]).format(na_rep="—", thousands=".", decimal=",")
    st.dataframe(styled, use_container_width=True, height=520)

    csv = df_table.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig")
    st.download_button("⬇️ Exportar CSV", csv, f"cot_{commodity.lower()}_{categoria.replace('/', '_').replace(' ', '_')}.csv", mime="text/csv")

st.markdown(f"""
<div class="footer">
    Fonte: CFTC – Commitments of Traders (COT) · CBOT · Atualização semanal às sextas-feiras<br>
    Arquivo carregado: {DATA_PATH}<br>
    Dashboard AgroBasis · Dados para análise de mercado
</div>
""", unsafe_allow_html=True)
