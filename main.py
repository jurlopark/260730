import json
import requests
import pandas as pd
import streamlit as st
import plotly.express as px

# ==========================================================
# 전국 시군구 고령화 지도
# ----------------------------------------------------------
# - 가장 최신 연도 사용
# - 읍면동 데이터를 시군구 단위로 합산
# - 65세 이상 인구 비율 계산
# - 시군구 경계 GeoJSON과 코드(5자리)로 연결
# ==========================================================

st.set_page_config(
    page_title="전국 시군구 고령화 지도",
    layout="wide"
)

st.title("🧓 전국 시군구 고령화 지도")
st.caption("시군구별 65세 이상 인구 비율 (가장 최신 연도)")


# ----------------------------------------------------------
# 데이터 주소
# ----------------------------------------------------------
POP_URL = "https://raw.githubusercontent.com/greatsong/modudata/main/data/population_yearly.csv.gz"
GEO_URL = "https://raw.githubusercontent.com/greatsong/modudata/main/data/boundaries/sigungu_kr.geojson"


# ----------------------------------------------------------
# 인구 데이터 읽기
# 코드 열은 반드시 문자열로 읽는다.
# ----------------------------------------------------------
@st.cache_data
def load_population():

    df = pd.read_csv(
        POP_URL,
        compression="gzip",
        dtype={"코드": str}
    )

    return df


# ----------------------------------------------------------
# GeoJSON 읽기
# ----------------------------------------------------------
@st.cache_data
def load_geojson():

    response = requests.get(GEO_URL)
    response.raise_for_status()

    return response.json()


# ----------------------------------------------------------
# 가장 최신 연도 데이터로 시군구 고령화율 계산
# ----------------------------------------------------------
@st.cache_data
def make_sigungu_table(df):

    # 최신 연도
    latest_year = df["연도"].max()

    df = df[df["연도"] == latest_year].copy()

    # 시군구 코드 (앞 5자리)
    df["시군구코드"] = df["코드"].str[:5]

    # ------------------------------------------------------
    # 전체 인구 열 찾기
    # ------------------------------------------------------
    total_cols = [c for c in df.columns if c.startswith("계_")]

    # ------------------------------------------------------
    # 65세 이상 열 찾기
    # ------------------------------------------------------
    old_cols = []

    for col in total_cols:

        age = col.replace("계_", "")

        if age == "100세 이상":
            old_cols.append(col)
            continue

        if age.endswith("세"):
            try:
                num = int(age.replace("세", ""))
                if num >= 65:
                    old_cols.append(col)
            except:
                pass

    # 읍면동별 전체 인구
    df["전체인구"] = df[total_cols].sum(axis=1)

    # 읍면동별 65세 이상 인구
    df["고령인구"] = df[old_cols].sum(axis=1)

    # 시군구 단위 합산
    sigungu = (
        df.groupby(
            ["시군구코드", "시도", "시군구"],
            as_index=False
        )[["전체인구", "고령인구"]]
        .sum()
    )

    sigungu["고령화율"] = sigungu["고령인구"] / sigungu["전체인구"] * 100

    return latest_year, sigungu


# ----------------------------------------------------------
# 고령화율을 5단계로 구분
# ----------------------------------------------------------
def make_class(rate):

    if rate < 19:
        return "19% 미만"
    elif rate < 23:
        return "19~23%"
    elif rate < 28:
        return "23~28%"
    elif rate < 38:
        return "28~38%"
    else:
        return "38% 이상"


# ----------------------------------------------------------
# 데이터 불러오기
# ----------------------------------------------------------
population = load_population()
geojson = load_geojson()

latest_year, sigungu = make_sigungu_table(population)

sigungu["등급"] = sigungu["고령화율"].apply(make_class)

st.subheader(f"{latest_year}년 시군구별 65세 이상 인구 비율")


# ----------------------------------------------------------
# 5단계 색상
# (낮은 값은 옅게, 높은 값은 진하게)
# ----------------------------------------------------------
color_map = {
    "19% 미만": "#f7fbff",
    "19~23%": "#c6dbef",
    "23~28%": "#6baed6",
    "28~38%": "#2171b5",
    "38% 이상": "#08306b"
}

category_order = {
    "등급": [
        "19% 미만",
        "19~23%",
        "23~28%",
        "28~38%",
        "38% 이상"
    ]
}


# ----------------------------------------------------------
# Plotly 단계구분도
# ----------------------------------------------------------
fig = px.choropleth(
    sigungu,
    geojson=geojson,
    locations="시군구코드",
    featureidkey="properties.코드",
    color="등급",
    color_discrete_map=color_map,
    category_orders=category_order,
    hover_name="시군구",
    hover_data={
        "시도": True,
        "고령화율": ":.2f",
        "시군구코드": False,
        "등급": False
    }
)

fig.update_geos(
    fitbounds="locations",
    visible=False,
    showcountries=False,
    showcoastlines=False,
    showland=False,
    showframe=False,
    bgcolor="rgba(0,0,0,0)"
)

fig.update_traces(
    marker_line_color="white",
    marker_line_width=0.5,
    hovertemplate=(
        "<b>%{hovertext}</b><br>"
        "시도: %{customdata[0]}<br>"
        "고령화율: %{customdata[1]:.2f}%"
        "<extra></extra>"
    )
)

fig.update_layout(
    height=850,
    margin=dict(l=0, r=0, t=0, b=0),
    legend_title_text="고령화율",
    paper_bgcolor="white",
    plot_bgcolor="white"
)

st.plotly_chart(fig, use_container_width=True)


# ----------------------------------------------------------
# 상위/하위 10개
# ----------------------------------------------------------
high = (
    sigungu.sort_values("고령화율", ascending=False)
    [["시도", "시군구", "고령화율"]]
    .head(10)
    .copy()
)

low = (
    sigungu.sort_values("고령화율")
    [["시도", "시군구", "고령화율"]]
    .head(10)
    .copy()
)

high["고령화율"] = high["고령화율"].map(lambda x: f"{x:.2f}%")
low["고령화율"] = low["고령화율"].map(lambda x: f"{x:.2f}%")

col1, col2 = st.columns(2)

with col1:
    st.subheader("고령화율 높은 시군구 TOP 10")
    st.dataframe(
        high,
        use_container_width=True,
        hide_index=True
    )

with col2:
    st.subheader("고령화율 낮은 시군구 TOP 10")
    st.dataframe(
        low,
        use_container_width=True,
        hide_index=True
    )
