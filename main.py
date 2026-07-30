# -*- coding: utf-8 -*-
"""
전국 중학생 남녀 비율 지도
- 인구 데이터: 읍면동 단위 연령별 인구 (2015~2026)
- 지도 경계 데이터: 시군구 단위 GeoJSON
- '코드' 앞 5자리로 두 데이터를 연결합니다.
"""

import json

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import streamlit as st
from plotly.subplots import make_subplots

# -----------------------------
# 기본 설정
# -----------------------------
st.set_page_config(page_title="전국 중학생 남녀 비율 지도", layout="wide")

POP_URL = "https://raw.githubusercontent.com/greatsong/modudata/main/data/population_yearly.csv.gz"
GEO_URL = "https://raw.githubusercontent.com/greatsong/modudata/main/data/boundaries/sigungu_kr.geojson"

# 중학생으로 볼 나이 (통계청 기준: 만 12~14세)
MS_AGES = [12, 13, 14]


# -----------------------------
# 데이터 불러오기 (캐시 사용: 매번 새로 안 받아오게 함)
# -----------------------------
@st.cache_data(show_spinner="인구 데이터를 불러오는 중...")
def load_population():
    # 필요한 열만 골라서 불러오면 훨씬 빠릅니다.
    male_cols = [f"남_{age}세" for age in MS_AGES]
    female_cols = [f"여_{age}세" for age in MS_AGES]
    use_cols = ["연도", "시도", "시군구", "동", "코드"] + male_cols + female_cols

    df = pd.read_csv(
        POP_URL,
        compression="gzip",
        dtype={"코드": str},  # 코드는 숫자가 아니라 이름표! 반드시 문자로 읽기
        usecols=use_cols,
    )

    # 코드 앞 5자리 = 시군구 코드
    df["시군구코드"] = df["코드"].str[:5]

    # 중학생 남/여 인구 계산 (나이별 열을 더함)
    df["남_중학생"] = df[male_cols].sum(axis=1)
    df["여_중학생"] = df[female_cols].sum(axis=1)

    return df[["연도", "시도", "시군구", "시군구코드", "남_중학생", "여_중학생"]]


@st.cache_data(show_spinner="지도 경계 데이터를 불러오는 중...")
def load_geojson():
    res = requests.get(GEO_URL)
    return json.loads(res.text)


df_raw = load_population()
geojson_data = load_geojson()

# -----------------------------
# 연도 + 시군구 단위로 합치기
# -----------------------------
yearly = (
    df_raw.groupby(["연도", "시군구코드"], as_index=False)
    .agg(시도=("시도", "first"), 시군구=("시군구", "first"),
         남_중학생=("남_중학생", "sum"), 여_중학생=("여_중학생", "sum"))
)
yearly["전체_중학생"] = yearly["남_중학생"] + yearly["여_중학생"]
# 중학생이 한 명도 없는 지역은 비율을 계산할 수 없으므로 제외
yearly = yearly[yearly["전체_중학생"] > 0].copy()
yearly["남자비율"] = yearly["남_중학생"] / yearly["전체_중학생"] * 100
yearly["여자비율"] = 100 - yearly["남자비율"]
yearly["지역명"] = yearly["시도"] + " " + yearly["시군구"]

# -----------------------------
# 가장 최신 연도 데이터만 뽑기 (지도용)
# -----------------------------
latest_year = int(yearly["연도"].max())
latest = yearly[yearly["연도"] == latest_year].copy()

# -----------------------------
# 남자 비율 구간 나누기 (5단계, 범례에 % 구간 글자로 표시)
# -----------------------------
n_bins = 5
_, bin_edges = pd.qcut(latest["남자비율"], q=n_bins, duplicates="drop", retbins=True)
bin_edges = np.unique(np.round(bin_edges, 0))
n_bins = len(bin_edges) - 1  # duplicates 로 인해 구간 수가 줄어들 수 있음

labels = []
for i in range(n_bins):
    if i == 0:
        labels.append(f"{bin_edges[i + 1]:.0f}% 미만")
    elif i == n_bins - 1:
        labels.append(f"{bin_edges[i]:.0f}% 이상")
    else:
        labels.append(f"{bin_edges[i]:.0f}~{bin_edges[i + 1]:.0f}%")

latest["남자비율구간"] = pd.cut(
    latest["남자비율"], bins=bin_edges, labels=labels, include_lowest=True
)

# 파란색(여자 많음) -> 빨간색(남자 많음) 순서의 색
color_anchor = ["#2166ac", "#67a9cf", "#f7f7f7", "#ef8a62", "#b2182b"]
if n_bins > 1:
    positions = [i / (n_bins - 1) for i in range(n_bins)]
else:
    positions = [0.5]
sampled_colors = px.colors.sample_colorscale(color_anchor, positions)
color_map = dict(zip(labels, sampled_colors))

# -----------------------------
# 화면 제목
# -----------------------------
st.title("🏫 전국 중학생 남녀 비율 지도")
st.caption(f"기준 연도: {latest_year}년 · 중학생 = 만 12~14세 인구 기준")

# -----------------------------
# 지도 그리기
# -----------------------------
fig_map = px.choropleth(
    latest,
    geojson=geojson_data,
    locations="시군구코드",
    featureidkey="properties.코드",  # geojson 속성의 '코드'와 매칭
    color="남자비율구간",
    color_discrete_map=color_map,
    category_orders={"남자비율구간": labels},
    custom_data=["시군구", "시도", "남자비율", "여자비율"],
)

# 마우스를 올렸을 때 보여줄 정보
fig_map.update_traces(
    hovertemplate=(
        "<b>%{customdata[0]}</b> (%{customdata[1]})<br>"
        "남자: %{customdata[2]:.1f}%<br>"
        "여자: %{customdata[3]:.1f}%<extra></extra>"
    ),
    marker_line_color="white",
    marker_line_width=0.5,
)

# 배경 지도 타일 없이 경계선만 보이도록 설정
fig_map.update_geos(visible=False, fitbounds="locations")
fig_map.update_layout(
    legend_title_text="남자 비율 구간",
    margin=dict(l=0, r=0, t=10, b=0),
    height=650,
)

st.plotly_chart(fig_map, use_container_width=True)

# -----------------------------
# 12년간 남녀 비율 변화 그래프
# -----------------------------
st.subheader(f"📈 {yearly['연도'].min()}년 ~ {yearly['연도'].max()}년 남자 비율 변화")

n_years = yearly["연도"].nunique()

# 지역(시군구코드)별로 연도별 남자비율을 표 형태로 펼치기
pivot = yearly.pivot_table(index="시군구코드", columns="연도", values="남자비율")

# 모든 연도 자료가 다 있는 지역만 변동 비교 대상으로 사용
pivot_full = pivot.dropna()
변동폭 = pivot_full.max(axis=1) - pivot_full.min(axis=1)

top5_big = 변동폭.sort_values(ascending=False).head(5)   # 변동 가장 큰 5곳
top5_small = 변동폭.sort_values(ascending=True).head(5)  # 변동 가장 작은 5곳

# 지역명 매핑 (시군구코드 -> 지역명)
name_map = yearly.drop_duplicates("시군구코드").set_index("시군구코드")["지역명"]

fig_trend = make_subplots(
    rows=1, cols=2,
    subplot_titles=("남자 비율 변동이 가장 큰 지역 TOP 5", "남자 비율 변동이 가장 작은 지역 TOP 5"),
)

for code in top5_big.index:
    sub = yearly[yearly["시군구코드"] == code].sort_values("연도")
    fig_trend.add_trace(
        go.Scatter(x=sub["연도"], y=sub["남자비율"], mode="lines+markers",
                    name=name_map[code]),
        row=1, col=1,
    )

for code in top5_small.index:
    sub = yearly[yearly["시군구코드"] == code].sort_values("연도")
    fig_trend.add_trace(
        go.Scatter(x=sub["연도"], y=sub["남자비율"], mode="lines+markers",
                    name=name_map[code]),
        row=1, col=2,
    )

fig_trend.update_xaxes(title_text="연도")
fig_trend.update_yaxes(title_text="남자 비율(%)")
fig_trend.update_layout(height=450, legend_title_text="지역")

st.plotly_chart(fig_trend, use_container_width=True)

with st.expander("ℹ️ 데이터 안내"):
    st.write(
        f"- 중학생 인구는 만 {MS_AGES[0]}~{MS_AGES[-1]}세 인구 합계로 계산했습니다.\n"
        "- 지도는 읍·면·동 인구를 시군구 단위로 합쳐서 만들었습니다.\n"
        "- 지역 매칭은 이름이 아닌 행정구역 코드(5자리)로 진행했습니다.\n"
        f"- 변동 그래프는 {n_years}개 연도 자료가 모두 있는 지역만 대상으로 계산했습니다."
    )
