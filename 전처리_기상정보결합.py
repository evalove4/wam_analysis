import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import io

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
    """서창교측정소 데이터 로드 및 전처리"""
    try:
        df = pd.read_excel(file)
        # 헤더가 복잡한 경우 처리
        if df.iloc[0].isnull().sum() > len(df.columns) * 0.5:
            # 첫 번째 행이 대부분 비어있으면 스킵
            df = df.iloc[2:].reset_index(drop=True)
            df.columns = [f"col_{i}" if pd.isna(col) else str(col) for i, col in enumerate(df.columns)]
        
        # 측정일시 컬럼 찾기 및 변환
        datetime_col = None
        for col in df.columns:
            if '측정일시' in str(col) or '시간' in str(col):
                datetime_col = col
                break
        
        if datetime_col:
            df[datetime_col] = pd.to_datetime(df[datetime_col], errors='coerce')
            df = df.dropna(subset=[datetime_col])
            df = df.sort_values(datetime_col)
            df.rename(columns={datetime_col: '측정시간'}, inplace=True)
        
        return df
    except Exception as e:
        st.error(f"수질 데이터 로드 중 오류: {str(e)}")
        return None

def merge_data(weather_df, water_df):
    """기상 데이터와 수질 데이터 결합"""
    try:
        # 시간 기준으로 병합
        weather_df_copy = weather_df.copy()
        water_df_copy = water_df.copy()
        
        # 시간 컬럼 이름 통일
        if '일시' in weather_df_copy.columns:
            weather_df_copy.rename(columns={'일시': '측정시간'}, inplace=True)
        
        # 가장 가까운 시간으로 병합 (1시간 이내)
        merged_data = []
        
        for _, water_row in water_df_copy.iterrows():
            water_time = water_row['측정시간']
            
            # 가장 가까운 기상 데이터 찾기 (1시간 이내)
            time_diff = abs(weather_df_copy['측정시간'] - water_time)
            closest_idx = time_diff.idxmin()
            
            if time_diff.loc[closest_idx] <= pd.Timedelta(hours=1):
                weather_row = weather_df_copy.loc[closest_idx]
                
                # 데이터 결합
                combined_row = water_row.copy()
                for col in weather_df_copy.columns:
                    if col != '측정시간':
                        combined_row[f'기상_{col}'] = weather_row[col]
                
                merged_data.append(combined_row)
        
        if merged_data:
            result_df = pd.DataFrame(merged_data)
            result_df.reset_index(drop=True, inplace=True)
            result_df.insert(0, 'No', range(1, len(result_df) + 1))
            return result_df
        else:
            st.error("병합할 수 있는 데이터가 없습니다. 시간 범위를 확인해주세요.")
            return None
            
    except Exception as e:
        st.error(f"데이터 병합 중 오류: {str(e)}")
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
                
                # 미리보기
                with st.expander("데이터 미리보기"):
                    st.dataframe(weather_df.head())
    
    with col2:
        st.subheader("🏭 서창교측정소 데이터")
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
                
                # 미리보기
                with st.expander("데이터 미리보기"):
                    st.dataframe(water_df.head())
    
    # 데이터 결합
    st.markdown("---")
    st.header("🔄 데이터 결합")
    
    if st.session_state.weather_data is not None and st.session_state.water_data is not None:
        if st.button("🚀 데이터 결합 실행", type="primary"):
            with st.spinner("데이터를 결합하는 중..."):
                merged_df = merge_data(st.session_state.weather_data, st.session_state.water_data)
                
                if merged_df is not None:
                    st.session_state.merged_data = merged_df
                    st.success("✅ 데이터 결합 완료!")
                    st.write(f"📊 결합된 데이터 크기: {merged_df.shape[0]}행 × {merged_df.shape[1]}열")
                    
                    # 결합 결과 미리보기
                    with st.expander("결합된 데이터 미리보기"):
                        st.dataframe(merged_df.head())
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
        st.write(f"**전체 데이터 포인트:** {len(df):,}개")
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
            st.dataframe(missing_df)
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
        
        if quality_metrics:
            for metric, value in quality_metrics.items():
                st.write(f"**{metric}:** {value}")
        
        # 월별 통계
        st.subheader("📅 월별 통계")
        
        df['월'] = df['측정시간'].dt.month
        monthly_stats = df.groupby('월').agg({
            '수소이온농도': ['mean', 'std'],
            '용존산소': ['mean', 'std'],
            '수온': ['mean', 'std']
        }).round(2)
        
        if not monthly_stats.empty:
            st.dataframe(monthly_stats)
    
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
            filename = f"용봉측정소_결합데이터_{current_time}.xlsx"
            
            # Excel 파일 생성
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df.to_excel(writer, sheet_name='용봉측정소_데이터', index=False)
                
                # 워크시트 서식 설정
                workbook = writer.book
                worksheet = writer.sheets['용봉측정소_데이터']
                
                # 헤더 서식
                header_format = workbook.add_format({
                    'bold': True,
                    'text_wrap': True,
                    'valign': 'top',
                    'fg_color': '#D7E4BD',
                    'border': 1
                })
                
                # 헤더 적용
                for col_num, value in enumerate(df.columns.values):
                    worksheet.write(0, col_num, value, header_format)
                    worksheet.set_column(col_num, col_num, 15)  # 컬럼 너비 설정
            
            output.seek(0)
            
            st.download_button(
                label="📥 Excel 파일 다운로드",
                data=output.getvalue(),
                file_name=filename,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        
        else:  # CSV 형식
            filename = f"용봉측정소_결합데이터_{current_time}.csv"
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
        info_col1, info_col2, info_col3 = st.columns(3)
        
        with info_col1:
            st.metric("총 레코드 수", f"{df.shape[0]:,}")
        
        with info_col2:
            st.metric("총 컬럼 수", df.shape[1])
        
        with info_col3:
            date_range = (df['측정시간'].max() - df['측정시간'].min()).days
            st.metric("측정 기간 (일)", date_range)
        
        # 컬럼 정보
        st.subheader("📊 컬럼 정보")
        column_info = []
        for col in df.columns:
            dtype = str(df[col].dtype)
            non_null = df[col].count()
            null_count = df[col].isnull().sum()
            
            column_info.append({
                '컬럼명': col,
                '데이터 타입': dtype,
                '유효 데이터 수': non_null,
                '결측치 수': null_count,
                '결측치 비율(%)': round(null_count / len(df) * 100, 2)
            })
        
        column_df = pd.DataFrame(column_info)
        st.dataframe(column_df, use_container_width=True)
    
    else:
        st.info("💡 먼저 데이터를 업로드하고 결합해주세요.")

# 사이드바 추가 정보
st.sidebar.markdown("---")
st.sidebar.markdown("### ℹ️ 시스템 정보")
st.sidebar.markdown("""
**개발 목적**: 광주 지역 수질 및 기상 데이터 통합 분석

**주요 기능**:
- 기상청 데이터와 수질 측정 데이터 결합
- 실시간 데이터 시각화
- 통계 분석 및 품질 평가
- 결합된 데이터 다운로드

**데이터 소스**:
- 광주기상대: 기상 정보
- 서창교측정소: 수질 측정 데이터
- 용봉측정소: 통합 결과 데이터
""")

# 푸터
st.markdown("---")
st.markdown(
    "<div style='text-align: center; color: gray;'>"
    "🌊 광주 수질-기상 데이터 통합 시스템 v1.0 | "
    "Developed with Streamlit"
    "</div>",
    unsafe_allow_html=True
)

# 사용 방법 안내
if st.sidebar.button("📖 사용 방법"):
    st.sidebar.markdown("""
    ### 📖 사용 방법
    
    1. **데이터 업로드**: 
       - 광주기상대 Excel 파일 업로드
       - 서창교측정소 Excel 파일 업로드
    
    2. **데이터 결합**: 
       - '데이터 결합 실행' 버튼 클릭
       - 시간 기준으로 자동 매칭
    
    3. **시각화**: 
       - 다양한 차트와 그래프로 데이터 분석
       - 시계열, 상관관계, 분포 분석
    
    4. **통계 분석**: 
       - 기본 통계 정보 확인
       - 수질 기준 평가
    
    5. **다운로드**: 
       - Excel 또는 CSV 형식으로 저장
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
        required_cols = ['일시', '기온(°C)']
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