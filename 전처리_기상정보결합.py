import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import io
import xlsxwriter

# 페이지 설정
st.set_page_config(
    page_title="광주 수질-기상 데이터 통합 시스템",
    page_icon="🌊",
    layout="wide"
)

st.title("🌊 광주 수질-기상 데이터 통합 시스템")
st.markdown("---")

# 사이드바 메뉴
st.sidebar.title("📊 메뉴")
menu = st.sidebar.selectbox(
    "작업 선택",
    ["데이터 업로드 및 결합", "데이터 시각화", "통계 분석", "데이터 다운로드"]
)

# 세션 상태 초기화
if 'merged_data' not in st.session_state:
    st.session_state.merged_data = None
if 'weather_data' not in st.session_state:
    st.session_state.weather_data = None
if 'water_data' not in st.session_state:
    st.session_state.water_data = None

def load_weather_data(file):
    """광주기상대 데이터 로드 및 전처리"""
    try:
        df = pd.read_excel(file)
        # 컬럼명 정리
        df.columns = df.columns.str.strip()
        # 일시 컬럼을 datetime으로 변환
        if '일시' in df.columns:
            df['일시'] = pd.to_datetime(df['일시'])
            df = df.sort_values('일시')
        return df
    except Exception as e:
        st.error(f"기상 데이터 로드 중 오류: {str(e)}")
        return None

def load_water_data(file):
    """수질측정소 데이터 로드 및 전처리 (수정된 버전)"""
    try:
        # 원본 데이터 읽기 (헤더 없이)
        df_raw = pd.read_excel(file, header=None)
        
        st.info("📊 파일 구조 분석 중...")
        
        # 헤더 구조 분석
        header_row1 = df_raw.iloc[0].values  # ["No", "서창교", "수소이온농도", ...]
        header_row2 = df_raw.iloc[1].values  # [null, "측정일시", "-", ...]
        header_row3 = df_raw.iloc[2].values  # [null, null, "측정값", "측정상태", ...]
        
        # 새로운 컬럼명 생성
        new_columns = []
        for i in range(len(header_row1)):
            if i == 0:
                new_columns.append("No")
            elif i == 1:
                new_columns.append("측정시간")  # 측정일시 -> 측정시간으로 통일
            else:
                # 측정항목명과 측정값/상태 조합
                main_col = header_row1[i] if pd.notna(header_row1[i]) else ""
                sub_col = header_row3[i] if pd.notna(header_row3[i]) else ""
                
                if main_col and sub_col:
                    if sub_col == "측정값":
                        new_columns.append(main_col)
                    else:
                        new_columns.append(f"{main_col}_{sub_col}")
                elif main_col:
                    new_columns.append(main_col)
                else:
                    new_columns.append(f"col_{i}")
        
        # 실제 데이터 추출 (3행부터)
        df = df_raw.iloc[3:].copy()
        df.columns = new_columns[:len(df.columns)]
        
        # 측정시간 컬럼 처리
        if '측정시간' in df.columns:
            # 시간 데이터 변환
            df['측정시간'] = pd.to_datetime(df['측정시간'], errors='coerce')
            # 유효하지 않은 시간 데이터 제거
            initial_count = len(df)
            df = df.dropna(subset=['측정시간'])
            final_count = len(df)
            
            if initial_count != final_count:
                st.warning(f"⚠️ 유효하지 않은 시간 데이터 {initial_count - final_count}개 제거됨")
            
            df = df.sort_values('측정시간')
        else:
            st.error("❌ 측정시간 컬럼을 찾을 수 없습니다.")
            return None
        
        # 숫자형 데이터 변환
        numeric_columns = ['수소이온농도', '용존산소', '전기전도도', '수온', '탁도', 
                          '총유기탄소', '클로로필-a', '남조류']
        
        for col in numeric_columns:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
        # 인덱스 재설정
        df.reset_index(drop=True, inplace=True)
        
        # 컬럼 정보 표시
        detected_columns = [col for col in df.columns if col in numeric_columns + ['측정시간']]
        st.success(f"✅ 수질 데이터 로드 완료")
        st.info(f"🔍 감지된 주요 컬럼: {detected_columns}")
        
        return df
        
    except Exception as e:
        st.error(f"❌ 수질 데이터 로드 중 오류: {str(e)}")
        st.error(f"상세 오류: {type(e).__name__}")
        return None

def merge_data(weather_df, water_df):
    """기상 데이터와 수질 데이터 결합 (수정된 버전)"""
    try:
        # 데이터 복사
        weather_df_copy = weather_df.copy()
        water_df_copy = water_df.copy()
        
        # 시간 컬럼 이름 통일
        time_columns_weather = ['일시', '측정시간', '시간']
        time_columns_water = ['측정시간', '측정일시', '시간']
        
        # 기상 데이터 시간 컬럼 찾기
        weather_time_col = None
        for col in time_columns_weather:
            if col in weather_df_copy.columns:
                weather_time_col = col
                break
        
        if weather_time_col is None:
            st.error("❌ 기상 데이터에서 시간 컬럼을 찾을 수 없습니다.")
            return None
        
        if weather_time_col != '측정시간':
            weather_df_copy.rename(columns={weather_time_col: '측정시간'}, inplace=True)
        
        # 수질 데이터 시간 컬럼 확인
        if '측정시간' not in water_df_copy.columns:
            st.error("❌ 수질 데이터에서 측정시간 컬럼을 찾을 수 없습니다.")
            return None
        
        # 시간 데이터 타입 확인 및 변환
        if not pd.api.types.is_datetime64_any_dtype(weather_df_copy['측정시간']):
            weather_df_copy['측정시간'] = pd.to_datetime(weather_df_copy['측정시간'], errors='coerce')
        
        if not pd.api.types.is_datetime64_any_dtype(water_df_copy['측정시간']):
            water_df_copy['측정시간'] = pd.to_datetime(water_df_copy['측정시간'], errors='coerce')
        
        # 결측 시간 데이터 제거
        weather_df_copy = weather_df_copy.dropna(subset=['측정시간'])
        water_df_copy = water_df_copy.dropna(subset=['측정시간'])
        
        if len(weather_df_copy) == 0 or len(water_df_copy) == 0:
            st.error("❌ 유효한 시간 데이터가 없습니다.")
            return None
        
        # 시간 범위 확인
        weather_start = weather_df_copy['측정시간'].min()
        weather_end = weather_df_copy['측정시간'].max()
        water_start = water_df_copy['측정시간'].min()
        water_end = water_df_copy['측정시간'].max()
        
        # 겹치는 시간 범위 확인
        overlap_start = max(weather_start, water_start)
        overlap_end = min(weather_end, water_end)
        
        st.info(f"""
        📅 **시간 범위 정보:**
        - 기상 데이터: {weather_start} ~ {weather_end} ({len(weather_df_copy)}개)
        - 수질 데이터: {water_start} ~ {water_end} ({len(water_df_copy)}개)
        - 겹치는 범위: {overlap_start} ~ {overlap_end}
        """)
        
        if overlap_start >= overlap_end:
            st.error("❌ 두 데이터셋의 시간 범위가 겹치지 않습니다!")
            return None
        
        # 가장 가까운 시간으로 병합
        merged_data = []
        match_count = 0
        max_time_diff = pd.Timedelta(hours=1)
        
        progress_bar = st.progress(0)
        total_rows = len(water_df_copy)
        
        for idx, (_, water_row) in enumerate(water_df_copy.iterrows()):
            # 진행률 업데이트
            if idx % 100 == 0 or idx == total_rows - 1:
                progress_bar.progress((idx + 1) / total_rows)
            
            water_time = water_row['측정시간']
            
            # 겹치는 시간 범위 내의 데이터만 처리
            if water_time < overlap_start or water_time > overlap_end:
                continue
            
            # 가장 가까운 기상 데이터 찾기
            time_diff = abs(weather_df_copy['측정시간'] - water_time)
            min_diff_idx = time_diff.idxmin()
            min_diff = time_diff.loc[min_diff_idx]
            
            if min_diff <= max_time_diff:
                weather_row = weather_df_copy.loc[min_diff_idx]
                
                # 데이터 결합
                combined_row = water_row.copy()
                for col in weather_df_copy.columns:
                    if col != '측정시간':
                        # 기상 데이터 컬럼명에 접두사 추가
                        new_col_name = f'기상_{col}' if not col.startswith('기상_') else col
                        combined_row[new_col_name] = weather_row[col]
                
                merged_data.append(combined_row)
                match_count += 1
        
        progress_bar.empty()
        
        if merged_data:
            result_df = pd.DataFrame(merged_data)
            result_df.reset_index(drop=True, inplace=True)
            # No 컬럼 재생성
            if 'No' in result_df.columns:
                result_df['No'] = range(1, len(result_df) + 1)
            else:
                result_df.insert(0, 'No', range(1, len(result_df) + 1))
            
            success_rate = (match_count / len(water_df_copy)) * 100
            st.success(f"""
            ✅ **데이터 병합 완료!**
            - 매칭된 레코드: {match_count:,}개
            - 성공률: {success_rate:.1f}%
            - 최종 데이터 크기: {result_df.shape[0]}행 × {result_df.shape[1]}열
            """)
            
            return result_df
        else:
            st.error("❌ 병합할 수 있는 데이터가 없습니다. 시간 범위와 간격을 확인해주세요.")
            return None
            
    except Exception as e:
        st.error(f"❌ 데이터 병합 중 오류: {str(e)}")
        st.error(f"상세 오류: {type(e).__name__}")
        return None

# 메뉴별 기능 구현
if menu == "데이터 업로드 및 결합":
    st.header("📁 데이터 파일 업로드")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("🌤️ 광주기상대 데이터")
        weather_file = st.file_uploader(
            "기상 데이터 파일 업로드 (.xlsx)",
            type=['xlsx'],
            key='weather'
        )
        
        if weather_file:
            weather_df = load_weather_data(weather_file)
            if weather_df is not None:
                st.session_state.weather_data = weather_df
                st.success("✅ 기상 데이터 로드 완료")
                st.write(f"📊 데이터 크기: {weather_df.shape[0]}행 × {weather_df.shape[1]}열")
                
                # 시간 범위 표시
                if '일시' in weather_df.columns:
                    time_range = f"{weather_df['일시'].min()} ~ {weather_df['일시'].max()}"
                    st.write(f"⏰ 시간 범위: {time_range}")
                
                # 미리보기
                with st.expander("데이터 미리보기"):
                    st.dataframe(weather_df.head())
    
    with col2:
        st.subheader("🏭 수질자동측정소 데이터")
        water_file = st.file_uploader(
            "수질 측정 데이터 파일 업로드 (.xlsx)",
            type=['xlsx'],
            key='water'
        )
        
        if water_file:
            water_df = load_water_data(water_file)
            if water_df is not None:
                st.session_state.water_data = water_df
                st.success("✅ 수질 데이터 로드 완료")
                st.write(f"📊 데이터 크기: {water_df.shape[0]}행 × {water_df.shape[1]}열")
                
                # 시간 범위 표시
                if '측정시간' in water_df.columns:
                    time_range = f"{water_df['측정시간'].min()} ~ {water_df['측정시간'].max()}"
                    st.write(f"⏰ 시간 범위: {time_range}")
                
                # 미리보기
                with st.expander("데이터 미리보기"):
                    st.dataframe(water_df.head())
    
    # 데이터 결합
    st.markdown("---")
    st.header("🔄 데이터 결합")
    
    if st.session_state.weather_data is not None and st.session_state.water_data is not None:
        # 결합 옵션 설정
        st.subheader("⚙️ 결합 옵션")
        col1, col2 = st.columns(2)
        
        with col1:
            max_time_diff = st.selectbox(
                "최대 시간 차이 허용 범위",
                [1, 2, 3, 6, 12, 24],
                index=0,
                help="기상 데이터와 수질 데이터 간 최대 허용 시간 차이 (시간)"
            )
        
        with col2:
            merge_method = st.selectbox(
                "병합 방법",
                ["가장 가까운 시간", "정확한 시간만"],
                help="가장 가까운 시간: 허용 범위 내에서 가장 가까운 기상 데이터 매칭\n정확한 시간만: 정확히 일치하는 시간만 매칭"
            )
        
        if st.button("🚀 데이터 결합 실행", type="primary"):
            with st.spinner("데이터를 결합하는 중..."):
                merged_df = merge_data(st.session_state.weather_data, st.session_state.water_data)
                
                if merged_df is not None:
                    st.session_state.merged_data = merged_df
                    
                    # 결합 결과 미리보기
                    with st.expander("🔍 결합된 데이터 미리보기", expanded=True):
                        st.dataframe(merged_df.head(10))
                    
                    # 컬럼 정보 표시
                    st.subheader("📊 결합된 데이터 컬럼 정보")
                    water_cols = [col for col in merged_df.columns if not col.startswith('기상_') and col not in ['No', '측정시간']]
                    weather_cols = [col for col in merged_df.columns if col.startswith('기상_')]
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        st.write("**수질 측정 항목:**")
                        for col in water_cols[:10]:  # 상위 10개만 표시
                            st.write(f"• {col}")
                        if len(water_cols) > 10:
                            st.write(f"• ... 외 {len(water_cols)-10}개")
                    
                    with col2:
                        st.write("**기상 측정 항목:**")
                        for col in weather_cols[:10]:  # 상위 10개만 표시
                            st.write(f"• {col}")
                        if len(weather_cols) > 10:
                            st.write(f"• ... 외 {len(weather_cols)-10}개")
    else:
        st.info("💡 기상 데이터와 수질 데이터를 모두 업로드해주세요.")

elif menu == "데이터 시각화":
    st.header("📈 데이터 시각화")
    
    if st.session_state.merged_data is not None:
        df = st.session_state.merged_data
        
        # 시각화 옵션
        viz_type = st.selectbox(
            "시각화 유형 선택",
            ["시계열 분석", "상관관계 분석", "분포 분석", "다중 변수 대시보드"]
        )
        
        if viz_type == "시계열 분석":
            st.subheader("📊 시계열 분석")
            
            # 숫자형 컬럼 선택
            numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
            if 'No' in numeric_cols:
                numeric_cols.remove('No')
            
            selected_cols = st.multiselect(
                "분석할 변수 선택",
                numeric_cols,
                default=numeric_cols[:3] if len(numeric_cols) >= 3 else numeric_cols
            )
            
            if selected_cols and '측정시간' in df.columns:
                fig = make_subplots(
                    rows=len(selected_cols), cols=1,
                    shared_xaxes=True,
                    subplot_titles=selected_cols,
                    vertical_spacing=0.05
                )
                
                colors = px.colors.qualitative.Set1
                
                for i, col in enumerate(selected_cols):
                    fig.add_trace(
                        go.Scatter(
                            x=df['측정시간'],
                            y=df[col],
                            mode='lines+markers',
                            name=col,
                            line=dict(color=colors[i % len(colors)]),
                            marker=dict(size=4)
                        ),
                        row=i+1, col=1
                    )
                
                fig.update_layout(height=200*len(selected_cols), showlegend=False)
                fig.update_xaxes(title_text="시간", row=len(selected_cols), col=1)
                
                st.plotly_chart(fig, use_container_width=True)
        
        elif viz_type == "상관관계 분석":
            st.subheader("🔗 상관관계 분석")
            
            numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
            if 'No' in numeric_cols:
                numeric_cols.remove('No')
            
            if len(numeric_cols) > 1:
                corr_matrix = df[numeric_cols].corr()
                
                fig = px.imshow(
                    corr_matrix,
                    x=corr_matrix.columns,
                    y=corr_matrix.columns,
                    color_continuous_scale='RdBu_r',
                    aspect="auto",
                    title="변수 간 상관관계 히트맵"
                )
                fig.update_layout(height=600)
                st.plotly_chart(fig, use_container_width=True)
                
                # 높은 상관관계 표시
                st.subheader("높은 상관관계 (|r| > 0.7)")
                high_corr = []
                for i in range(len(corr_matrix.columns)):
                    for j in range(i+1, len(corr_matrix.columns)):
                        corr_val = corr_matrix.iloc[i, j]
                        if abs(corr_val) > 0.7:
                            high_corr.append({
                                '변수1': corr_matrix.columns[i],
                                '변수2': corr_matrix.columns[j],
                                '상관계수': round(corr_val, 3)
                            })
                
                if high_corr:
                    st.dataframe(pd.DataFrame(high_corr))
                else:
                    st.info("높은 상관관계를 보이는 변수 쌍이 없습니다.")
        
        elif viz_type == "분포 분석":
            st.subheader("📊 분포 분석")
            
            numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
            if 'No' in numeric_cols:
                numeric_cols.remove('No')
            
            selected_var = st.selectbox("분석할 변수 선택", numeric_cols)
            
            if selected_var:
                col1, col2 = st.columns(2)
                
                with col1:
                    # 히스토그램
                    fig_hist = px.histogram(
                        df, x=selected_var,
                        title=f"{selected_var} 분포",
                        nbins=30
                    )
                    st.plotly_chart(fig_hist, use_container_width=True)
                
                with col2:
                    # 박스 플롯
                    fig_box = px.box(
                        df, y=selected_var,
                        title=f"{selected_var} 박스 플롯"
                    )
                    st.plotly_chart(fig_box, use_container_width=True)
                
                # 기술통계
                st.subheader("기술통계")
                stats = df[selected_var].describe()
                st.dataframe(stats.to_frame().T)
        
        elif viz_type == "다중 변수 대시보드":
            st.subheader("🎛️ 다중 변수 대시보드")
            
            numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
            if 'No' in numeric_cols:
                numeric_cols.remove('No')
            
            # 주요 변수들 선택
            water_vars = [col for col in numeric_cols if any(keyword in col for keyword in ['수소이온농도', '용존산소', '전기전도도', '수온'])]
            weather_vars = [col for col in numeric_cols if any(keyword in col for keyword in ['기온', '습도', '강수량', '풍속'])]
            
            if water_vars and weather_vars and '측정시간' in df.columns:
                fig = make_subplots(
                    rows=2, cols=2,
                    subplot_titles=("수질 변수", "기상 변수", "수온 vs 기온", "습도 vs 용존산소"),
                    specs=[[{"secondary_y": False}, {"secondary_y": False}],
                           [{"secondary_y": False}, {"secondary_y": False}]]
                )
                
                # 수질 변수 (첫 번째)
                if len(water_vars) > 0:
                    fig.add_trace(
                        go.Scatter(x=df['측정시간'], y=df[water_vars[0]], 
                                 name=water_vars[0], mode='lines'),
                        row=1, col=1
                    )
                
                # 기상 변수 (첫 번째)
                if len(weather_vars) > 0:
                    fig.add_trace(
                        go.Scatter(x=df['측정시간'], y=df[weather_vars[0]], 
                                 name=weather_vars[0], mode='lines'),
                        row=1, col=2
                    )
                
                # 산점도들
                if '수온' in df.columns or any('수온' in col for col in df.columns):
                    temp_col = next((col for col in df.columns if '수온' in col), None)
                    air_temp_col = next((col for col in df.columns if '기온' in col), None)
                    
                    if temp_col and air_temp_col:
                        fig.add_trace(
                            go.Scatter(x=df[air_temp_col], y=df[temp_col], 
                                     mode='markers', name="수온 vs 기온"),
                            row=2, col=1
                        )
                
                fig.update_layout(height=800, showlegend=True)
                st.plotly_chart(fig, use_container_width=True)
    
    else:
        st.info("💡 먼저 데이터를 업로드하고 결합해주세요.")

elif menu == "통계 분석":
    st.header("📊 통계 분석")
    
    if st.session_state.merged_data is not None:
        df = st.session_state.merged_data
        
        # 기본 통계 정보
        st.subheader("📈 기본 통계 정보")
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("총 레코드 수", f"{len(df):,}")
        with col2:
            st.metric("총 컬럼 수", df.shape[1])
        with col3:
            date_range = (df['측정시간'].max() - df['측정시간'].min()).days
            st.metric("측정 기간 (일)", date_range)
        with col4:
            missing_rate = (df.isnull().sum().sum() / (df.shape[0] * df.shape[1]) * 100)
            st.metric("전체 결측률 (%)", f"{missing_rate:.1f}")
        
        st.write(f"**측정 기간:** {df['측정시간'].min()} ~ {df['측정시간'].max()}")
        
        # 결측치 분석
        st.subheader("🔍 결측치 분석")
        missing_data = df.isnull().sum()
        missing_data = missing_data[missing_data > 0].sort_values(ascending=False)
        
        if len(missing_data) > 0:
            missing_df = pd.DataFrame({
                '컬럼명': missing_data.index,
                '결측치 수': missing_data.values,
                '결측치 비율(%)': (missing_data.values / len(df) * 100).round(2)
            })
            
            # 상위 10개만 표시
            st.dataframe(missing_df.head(10))
            
            if len(missing_df) > 10:
                st.info(f"💡 총 {len(missing_df)}개 컬럼에 결측치가 있습니다. (상위 10개만 표시)")
        else:
            st.success("✅ 결측치가 없습니다!")
        
        # 수질 기준 평가
        st.subheader("🎯 수질 기준 평가")
        
        quality_metrics = {}
        
        # pH 평가
        if '수소이온농도' in df.columns:
            ph_data = df['수소이온농도'].dropna()
            if len(ph_data) > 0:
                good_ph = len(ph_data[(ph_data >= 6.5) & (ph_data <= 8.5)])
                quality_metrics['pH (6.5-8.5)'] = f"{good_ph}/{len(ph_data)} ({good_ph/len(ph_data)*100:.1f}%)"
        
        # 용존산소 평가 (5mg/L 이상 양호)
        if '용존산소' in df.columns:
            do_data = df['용존산소'].dropna()
            if len(do_data) > 0:
                good_do = len(do_data[do_data >= 5])
                quality_metrics['용존산소 (≥5mg/L)'] = f"{good_do}/{len(do_data)} ({good_do/len(do_data)*100:.1f}%)"
        
        # 수온 평가 (25°C 이하 양호)
        if '수온' in df.columns:
            temp_data = df['수온'].dropna()
            if len(temp_data) > 0:
                good_temp = len(temp_data[temp_data <= 25])
                quality_metrics['수온 (≤25°C)'] = f"{good_temp}/{len(temp_data)} ({good_temp/len(temp_data)*100:.1f}%)"
        
        if quality_metrics:
            for metric, value in quality_metrics.items():
                st.write(f"**{metric}:** {value}")
        else:
            st.info("💡 주요 수질 항목 (pH, 용존산소, 수온)이 데이터에 없습니다.")
        
        # 월별 통계
        st.subheader("📅 월별 통계")
        
        df['월'] = df['측정시간'].dt.month
        
        # 주요 수질 항목들의 월별 통계
        key_columns = ['수소이온농도', '용존산소', '수온', '전기전도도']
        available_columns = [col for col in key_columns if col in df.columns]
        
        if available_columns:
            monthly_stats = df.groupby('월')[available_columns].agg(['mean', 'std', 'min', 'max']).round(2)
            st.dataframe(monthly_stats)
        else:
            st.info("💡 월별 분석할 주요 수질 항목이 없습니다.")
        
        # 기상-수질 상관관계 분석
        st.subheader("🌤️ 기상-수질 상관관계")
        
        weather_cols = [col for col in df.columns if col.startswith('기상_')]
        water_cols = [col for col in df.columns if not col.startswith('기상_') and col not in ['No', '측정시간', '월']]
        
        if weather_cols and water_cols:
            # 상관계수가 높은 조합 찾기
            high_correlations = []
            
            for weather_col in weather_cols[:5]:  # 상위 5개 기상변수만
                for water_col in water_cols[:5]:  # 상위 5개 수질변수만
                    if df[weather_col].dtype in ['float64', 'int64'] and df[water_col].dtype in ['float64', 'int64']:
                        corr_val = df[weather_col].corr(df[water_col])
                        if not pd.isna(corr_val) and abs(corr_val) > 0.3:  # 0.3 이상만
                            high_correlations.append({
                                '기상변수': weather_col,
                                '수질변수': water_col,
                                '상관계수': round(corr_val, 3)
                            })
            
            if high_correlations:
                corr_df = pd.DataFrame(high_correlations)
                corr_df = corr_df.sort_values('상관계수', key=abs, ascending=False)
                st.dataframe(corr_df)
            else:
                st.info("💡 유의미한 기상-수질 상관관계가 발견되지 않았습니다.")
    
    else:
        st.info("💡 먼저 데이터를 업로드하고 결합해주세요.")

elif menu == "데이터 다운로드":
    st.header("💾 데이터 다운로드")
    
    if st.session_state.merged_data is not None:
        df = st.session_state.merged_data
        
        st.success(f"✅ 결합된 데이터 준비 완료 ({df.shape[0]}행 × {df.shape[1]}열)")
        
        # 다운로드 형식 선택
        format_type = st.selectbox(
            "다운로드 형식 선택",
            ["Excel (.xlsx)", "CSV (.csv)"]
        )
        
        # 파일 이름 설정
        current_time = datetime.now().strftime("%Y%m%d_%H%M%S")
        if format_type == "Excel (.xlsx)":
            filename = f"광주_수질기상_통합데이터_{current_time}.xlsx"
            
            # Excel 파일 생성
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df.to_excel(writer, sheet_name='통합데이터', index=False)
                
                # 워크시트 서식 설정
                workbook = writer.book
                worksheet = writer.sheets['통합데이터']
                
                # 헤더 서식
                header_format = workbook.add_format({
                    'bold': True,
                    'text_wrap': True,
                    'valign': 'top',
                    'fg_color': '#D7E4BD',
                    'border': 1
                })
                
                # 날짜 서식
                date_format = workbook.add_format({'num_format': 'yyyy-mm-dd hh:mm:ss'})
                
                # 헤더 적용
                for col_num, value in enumerate(df.columns.values):
                    worksheet.write(0, col_num, value, header_format)
                    
                    # 컬럼 너비 설정
                    if '시간' in str(value):
                        worksheet.set_column(col_num, col_num, 18)  # 시간 컬럼은 넓게
                    else:
                        worksheet.set_column(col_num, col_num, 12)
                
                # 날짜 컬럼 서식 적용
                if '측정시간' in df.columns:
                    time_col_idx = df.columns.get_loc('측정시간')
                    worksheet.set_column(time_col_idx, time_col_idx, 18, date_format)
            
            output.seek(0)
            
            st.download_button(
                label="📥 Excel 파일 다운로드",
                data=output.getvalue(),
                file_name=filename,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        
        else:  # CSV 형식
            filename = f"광주_수질기상_통합데이터_{current_time}.csv"
            csv_data = df.to_csv(index=False, encoding='utf-8-sig')
            
            st.download_button(
                label="📥 CSV 파일 다운로드",
                data=csv_data,
                file_name=filename,
                mime="text/csv"
            )
        
        # 데이터 미리보기
        st.subheader("📋 다운로드할 데이터 미리보기")
        st.dataframe(df.head(10))
        
        # 데이터 정보
        st.subheader("ℹ️ 데이터 정보")
        info_col1, info_col2, info_col3, info_col4 = st.columns(4)
        
        with info_col1:
            st.metric("총 레코드 수", f"{df.shape[0]:,}")
        
        with info_col2:
            st.metric("총 컬럼 수", df.shape[1])
        
        with info_col3:
            date_range = (df['측정시간'].max() - df['측정시간'].min()).days
            st.metric("측정 기간 (일)", date_range)
        
        with info_col4:
            file_size_mb = df.memory_usage(deep=True).sum() / 1024 / 1024
            st.metric("예상 파일 크기 (MB)", f"{file_size_mb:.1f}")
        
        # 컬럼 정보
        st.subheader("📊 컬럼 정보")
        
        # 수질/기상 컬럼 분류
        water_cols = [col for col in df.columns if not col.startswith('기상_') and col not in ['No', '측정시간']]
        weather_cols = [col for col in df.columns if col.startswith('기상_')]
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.write(f"**수질 측정 항목 ({len(water_cols)}개)**")
            for col in water_cols[:15]:  # 최대 15개까지만 표시
                non_null = df[col].count()
                null_count = df[col].isnull().sum()
                null_rate = round(null_count / len(df) * 100, 1)
                st.write(f"• {col}: {non_null:,}개 ({null_rate}% 결측)")
            if len(water_cols) > 15:
                st.write(f"• ... 외 {len(water_cols)-15}개 항목")
        
        with col2:
            st.write(f"**기상 측정 항목 ({len(weather_cols)}개)**")
            for col in weather_cols[:15]:  # 최대 15개까지만 표시
                non_null = df[col].count()
                null_count = df[col].isnull().sum()
                null_rate = round(null_count / len(df) * 100, 1)
                st.write(f"• {col}: {non_null:,}개 ({null_rate}% 결측)")
            if len(weather_cols) > 15:
                st.write(f"• ... 외 {len(weather_cols)-15}개 항목")
        
        # 데이터 품질 요약
        st.subheader("🎯 데이터 품질 요약")
        
        total_cells = df.shape[0] * df.shape[1]
        missing_cells = df.isnull().sum().sum()
        completeness = ((total_cells - missing_cells) / total_cells) * 100
        
        quality_col1, quality_col2, quality_col3 = st.columns(3)
        
        with quality_col1:
            st.metric("데이터 완성도", f"{completeness:.1f}%")
        
        with quality_col2:
            numeric_cols = len(df.select_dtypes(include=[np.number]).columns)
            st.metric("숫자형 컬럼 수", numeric_cols)
        
        with quality_col3:
            unique_dates = df['측정시간'].dt.date.nunique()
            st.metric("측정일 수", f"{unique_dates}일")
    
    else:
        st.info("💡 먼저 데이터를 업로드하고 결합해주세요.")

# 사이드바 추가 정보
st.sidebar.markdown("---")
st.sidebar.markdown("### ℹ️ 시스템 정보")
st.sidebar.markdown("""
**개발 목적**: 광주 지역 수질 및 기상 데이터 통합 분석

**주요 기능**:
- 다중 헤더 수질 데이터 자동 처리
- 기상청 데이터와 수질 측정 데이터 결합
- 실시간 데이터 시각화 및 분석
- 통계 분석 및 품질 평가
- 고품질 Excel/CSV 다운로드

**데이터 소스**:
- 광주기상대: 기상 정보
- 수질자동측정소: 수질 측정 데이터
- 통합 결과: 시간 기반 매칭 데이터

**v2.0 업데이트**:
- 복잡한 헤더 구조 자동 처리
- 향상된 에러 처리 및 진행률 표시
- 데이터 품질 분석 기능 추가
""")

# 푸터
st.markdown("---")
st.markdown(
    "<div style='text-align: center; color: gray;'>"
    "🌊 광주 수질-기상 데이터 통합 시스템 v2.0 | "
    "Developed with Streamlit | Enhanced Error Handling"
    "</div>",
    unsafe_allow_html=True
)

# 사용 방법 안내
if st.sidebar.button("📖 사용 방법"):
    st.sidebar.markdown("""
    ### 📖 사용 방법
    
    1. **데이터 업로드**: 
       - 광주기상대 Excel 파일 업로드
       - 수질측정소 Excel 파일 업로드
       - 복잡한 헤더 구조 자동 감지 및 처리
    
    2. **데이터 결합**: 
       - 시간 차이 허용 범위 설정 (1-24시간)
       - '데이터 결합 실행' 버튼 클릭
       - 시간 기준으로 자동 매칭
    
    3. **시각화**: 
       - 다양한 차트와 그래프로 데이터 분석
       - 시계열, 상관관계, 분포 분석
       - 다중 변수 대시보드
    
    4. **통계 분석**: 
       - 기본 통계 정보 및 데이터 품질 확인
       - 수질 기준 평가 및 월별 분석
       - 기상-수질 상관관계 분석
    
    5. **다운로드**: 
       - Excel 또는 CSV 형식으로 저장
       - 자동 서식 적용 및 품질 정보 포함
    """)

# 에러 처리 및 로깅
def log_error(error_msg):
    """에러 로깅 함수"""
    st.error(f"❌ 오류: {error_msg}")
    # 실제 운영 환경에서는 로그 파일에 기록

# 데이터 검증 함수
def validate_data(df, data_type):
    """데이터 유효성 검사"""
    if df is None or df.empty:
        return False, f"{data_type} 데이터가 비어있습니다."
    
    if data_type == "기상":
        required_cols = ['일시']
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            return False, f"필수 컬럼이 없습니다: {missing_cols}"
    
    elif data_type == "수질":
        if '측정시간' not in df.columns and not any('시간' in str(col) for col in df.columns):
            return False, "시간 정보 컬럼이 없습니다."
    
    return True, "데이터가 유효합니다."

# 성능 최적화를 위한 캐싱
@st.cache_data
def process_large_dataset(df):
    """대용량 데이터셋 처리 최적화"""
    return df.copy()

# 실시간 업데이트 기능 (향후 확장용)
def setup_realtime_update():
    """실시간 데이터 업데이트 설정"""
    # 실제 운영 환경에서는 데이터베이스 연결 등 구현
    pass

# 디버깅 정보 (개발자용)
if st.sidebar.button("🔧 디버깅 정보"):
    if st.session_state.merged_data is not None:
        df = st.session_state.merged_data
        st.sidebar.write("**데이터 타입 정보:**")
        for col in df.columns[:10]:  # 상위 10개만
            st.sidebar.write(f"{col}: {df[col].dtype}")
        
        st.sidebar.write(f"**메모리 사용량:** {df.memory_usage(deep=True).sum() / 1024 / 1024:.2f} MB")
        st.sidebar.write(f"**중복 행:** {df.duplicated().sum()}개")
    else:
        st.sidebar.write("데이터가 로드되지 않았습니다.")