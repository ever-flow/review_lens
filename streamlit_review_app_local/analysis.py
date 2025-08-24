import re
import os
import json            
import pandas as pd   
from konlpy.tag import Okt
from transformers import AutoTokenizer, AutoModelForSequenceClassification, pipeline
from sklearn.feature_extraction.text import TfidfVectorizer
# --- 상수 및 전역 설정 ---
try:
    okt = Okt()
    KONLPY_AVAILABLE = True
    print("KoNLPy Okt 형태소 분석기 로드 성공.")
except Exception as e:
    print(f"KoNLPy Okt 형태소 분석기 로드 실패: {e}")
    print("형태소 분석 기능이 비활성화됩니다. 기본 텍스트 클리닝만 사용됩니다.")
    KONLPY_AVAILABLE = False

try:
    tokenizer = AutoTokenizer.from_pretrained("WhitePeak/bert-base-cased-Korean-sentiment")
    model = AutoModelForSequenceClassification.from_pretrained("WhitePeak/bert-base-cased-Korean-sentiment")
    sentiment_analyzer = pipeline("sentiment-analysis", model=model, tokenizer=tokenizer)
    SENTIMENT_AVAILABLE = True
    print("감성 분석 모델 로드 성공.")
except Exception as e:
    print(f"감성 분석 모델 로드 중 오류 발생: {e}")
    print("모델 로드 없이 실행됩니다. 감성 분석 기능은 비활성화됩니다.")
    sentiment_analyzer = None
    SENTIMENT_AVAILABLE = False

# --- 불용어 설정 (기존 + 보강) ---
STOPWORDS = [
    '은','는','이','가','을','를','에게','한테','에서','으로','와','과','하고',
    '아','어','입니다','습니다','어요','아요','해요','한다','하는','했다','합니다',
    '있습니다','있어요','없습니다','없어요','같습니다','같아요','않습니다','않아요',
    '이다','되다','하다','있다','없다','정말','진짜','너무','아주','매우','좀','막',
    '그냥','잘','더','덜','그리고','그래서','하지만','근데','거나','든지','접기',
    '잇다','아니다','정도',
    '맛집','후기','리뷰','먹었어요','먹었다','왔어요','왔습니다','라고','이라고',
    'ㅋㅋ','ㅎㅎ','ㅠㅠ','ㅠ','ㅜㅜ','ㅜ','...', 'ㅡㅡ','!','?'
]

# --- 측면별 키워드 사전 (기존 + 보강) ---
ASPECT_KEYWORDS = {
    '가격': [
        '가격','비싸다','싸다','가성비','할인','금액','비용','가격대','지불하다',
        '아깝다','괜찮다','부담되다','저렴하다','합리적이다'
    ],
    '서비스': [
        '서비스','직원','친절하다','응대','대기','주문','알바생','사장님','서빙',
        '안내','설명','빠르다','느리다','불편하다','접객','응대','콜센터'
    ],
    '맛': [
        '맛','맛있다','맵다','달다','짜다','식감','싱겁다','고소하다','담백하다',
        '부드럽다','바삭하다','향','풍미','감칠맛','짜지','싱겁다'
    ],
    '분위기': [
        '분위기','인테리어','조용하다','시끄럽다','깔끔하다','아늑하다',
        '편안하다','음악','소음','테이블','조명','인테리어','공간','디자인'
    ],
    '메뉴': [
        '메뉴','음식','종류','다양하다','추천','시그니처','단품','세트','신메뉴',
        '특선','구성','맛보기','조합','신메뉴'
    ],
    '위치': [
        '위치','접근성','교통','주차','골목','멀다','가깝다','도보','차량','역세권',
        '주차장','찾기','오르막','내리막'
    ],
    '양': [
        '양','많다','적다','푸짐하다','모자라다','포만감','배부르다','남기다','리필'
    ]
}

def load_reviews(json_path: str = None, reviews_list: list = None) -> pd.DataFrame:
    reviews = []
    if json_path:
        if not os.path.exists(json_path):
            print(f"오류: 파일을 찾을 수 없습니다 - {json_path}")
            return pd.DataFrame(columns=['text'])
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            reviews = data.get('reviews', data) if isinstance(data, dict) else data
        except Exception as e:
            print(f"오류: JSON 파일 로딩 중 문제 발생 - {e}")
            return pd.DataFrame(columns=['text'])
    elif reviews_list is not None:
        reviews = reviews_list
    else:
        print("오류: json_path 또는 reviews_list 중 하나를 지정해야 합니다.")
        return pd.DataFrame(columns=['text'])

    if not reviews:
        print("데이터 로딩 완료: 리뷰 목록이 비어 있습니다.")
        return pd.DataFrame(columns=['text'])

    df = pd.DataFrame(reviews)
    df.columns = [c.lower() for c in df.columns]
    if 'text' not in df.columns:
        print(f"오류: 'text' 컬럼이 없습니다. 실제 컬럼: {df.columns.tolist()}")
        return pd.DataFrame(columns=['text'])

    print(f"총 {len(df)}개의 리뷰 데이터를 로드했습니다.")
    return df

def clean_and_tokenize(text: str) -> str:
    text = str(text).strip()
    text = re.sub(r'\s+', ' ', text)
    if not text:
        return ""
    if KONLPY_AVAILABLE:
        try:
            malist = okt.pos(text, norm=True, stem=True)
            words = [w for w, t in malist if t in ['Noun','Verb','Adjective'] and w not in STOPWORDS and len(w)>1]
            return ' '.join(words)
        except Exception:
            text = re.sub(r"[^가-힣a-zA-Z0-9 ]", " ", text)
            return re.sub(r"\s+", " ", text).strip()
    else:
        text = re.sub(r"[^가-힣a-zA-Z0-9 ]", " ", text)
        return re.sub(r"\s+", " ", text).strip()

def get_top_tfidf_keywords(corpus: list, top_n: int = 10) -> list:
    corpus = [d for d in corpus if d.strip()]
    if not corpus:
        return []
    #vectorizer = TfidfVectorizer(ngram_range=(1,2), max_features=1000)
    vectorizer = TfidfVectorizer(
        ngram_range=(1,2),
        max_features=1000,
        max_df=0.75,    # 문서의 75% 이상 나타나는 단어 제외
        min_df=5        # 최소 5개 문서에만 등장하는 단어만 사용
    )
    try:
        mat = vectorizer.fit_transform(corpus)
        sums = mat.sum(axis=0).A1
        features = vectorizer.get_feature_names_out()
        idx = sums.argsort()[::-1][:top_n]
        return [(features[i], round(sums[i],2)) for i in idx]
    except Exception:
        return []
def analyze_reviews(df: pd.DataFrame, pos_thresh: float = 0.9, neg_thresh: float = 0.9) -> tuple:
    if df.empty:
        print("분석할 리뷰 데이터가 없습니다.")
        return df, {}, 0, 0, pd.DataFrame(), pd.DataFrame(), {}, 0

    df['cleaned'] = df['text'].apply(clean_and_tokenize)

    if SENTIMENT_AVAILABLE:
        preds = sentiment_analyzer(df['cleaned'].tolist())
        df['sentiment'] = preds

        # 임계값 기반 레이블 매핑
        def label_map(si):
            lbl, sc = si.get('label'), si.get('score', 0.0)
            if lbl == 'LABEL_1' and sc >= pos_thresh:
                return '긍정'
            if lbl == 'LABEL_0' and sc >= neg_thresh:
                return '부정'
            return '중립'

        df['label'] = df['sentiment'].apply(label_map)
    else:
        df['sentiment'] = [{'label':'UNAVAILABLE','score':0.0}] * len(df)
        df['label'] = '분류불가'

    # 긍정·부정만 선택
    pos_df = df[df['label'] == '긍정'].copy()
    neg_df = df[df['label'] == '부정'].copy()
    total = len(pos_df) + len(neg_df)
    pos_ratio = (len(pos_df) / total * 100) if total else 0
    neg_ratio = (len(neg_df) / total * 100) if total else 0

    # 상위 리뷰 추출
    pos_df['score_val'] = pos_df['sentiment'].apply(lambda x: x.get('score', 0.0))
    neg_df['score_val'] = neg_df['sentiment'].apply(lambda x: x.get('score', 0.0))
    top_pos = pos_df.sort_values('score_val', ascending=False).head(20) ######
    top_neg = neg_df.sort_values('score_val', ascending=False).head(15) ######

    # 핵심 키워드
    all_corp = df['cleaned'].tolist()
    pos_corp = pos_df['cleaned'].tolist()
    neg_corp = neg_df['cleaned'].tolist()
    keywords = {
        '전체': get_top_tfidf_keywords(all_corp),
        '긍정': get_top_tfidf_keywords(pos_corp),
        '부정': get_top_tfidf_keywords(neg_corp)
    }

    # 측면별 키워드
    aspects = {}
    for asp, keys in ASPECT_KEYWORDS.items():
        corpus = df[df['cleaned'].apply(lambda x: any(k in x for k in keys))]['cleaned'].tolist()
        aspects[asp] = get_top_tfidf_keywords(corpus, top_n=5) if corpus else []

    return df, keywords, pos_ratio, neg_ratio, top_pos, top_neg, aspects, total



def generate_prompt(name, keywords, pos_ratio, neg_ratio, aspects, top_pos, top_neg, classified_count) -> str:
    def fmt(lst): return ', '.join([f"{w}({s})" for w,s in lst]) if lst else '없음'
    lines = []
    lines.append(f"### 리뷰 분석 요약: {name}\n")
    lines.append(f"- 리뷰 수 (감성 분석 성공): {classified_count}개")
    lines.append(f"- 긍정 비율: {pos_ratio:.1f}% | 부정 비율: {neg_ratio:.1f}%\n")

    lines.append("### 핵심 키워드")
    lines.append(f"- 전체: {fmt(keywords.get('전체', []))}")
    lines.append(f"- 긍정: {fmt(keywords.get('긍정', []))}")
    lines.append(f"- 부정: {fmt(keywords.get('부정', []))}\n")

    lines.append("### 측면별 키워드 (상위 5개)")
    for asp, kws in aspects.items():
        lines.append(f"- {asp}: {fmt(kws)}")

    lines.append("\n### 상위 긍정 리뷰")
    for i, row in enumerate(top_pos.itertuples(),1):
        lines.append(f"{i}. ({row.sentiment['score']:.3f}) {row.text}")
    lines.append("\n### 상위 부정 리뷰")
    for i, row in enumerate(top_neg.itertuples(),1):
        lines.append(f"{i}. ({row.sentiment['score']:.3f}) {row.text}")

    lines.append("\n### 요청사항")
    lines.append("1. 긍정적으로 평가되는 부분 (강점): 분석된 핵심 포인트 요약")
    lines.append("2. 개선이 필요한 부분 (약점): 주요 부정 키워드 및 원인 분석")
    lines.append("3. 실행 가능한 개선 방안: 구체적 제안 (측면별)")

    return "\n".join(lines)


### generate_prompt를 복사하되, 마지막 요청사항 부분만 소비자용(고객용)으로 바꾼 버전
def generate_consumer_prompt(name, keywords, pos_ratio, neg_ratio, aspects, top_pos, top_neg, classified_count) -> str:
    def fmt(lst): 
        return ', '.join(f"{w}({s})" for w, s in lst) if lst else '없음'

    lines = []
    lines.append(f"### 리뷰 분석 요약: {name}\n")
    lines.append(f"- 리뷰 수 (감성 분석 성공): {classified_count}개")
    lines.append(f"- 긍정 비율: {pos_ratio:.1f}% | 부정 비율: {neg_ratio:.1f}%\n")

    lines.append("### 핵심 키워드")
    lines.append(f"- 전체: {fmt(keywords.get('전체', []))}")
    lines.append(f"- 긍정: {fmt(keywords.get('긍정', []))}")
    lines.append(f"- 부정: {fmt(keywords.get('부정', []))}\n")

    lines.append("### 측면별 키워드 (상위 5개)")
    for asp, kws in aspects.items():
        lines.append(f"- {asp}: {fmt(kws)}")

    lines.append("\n### 상위 긍정 리뷰")
    for i, row in enumerate(top_pos.itertuples(), 1):
        lines.append(f"{i}. ({row.sentiment['score']:.3f}) {row.text}")
    lines.append("\n### 상위 부정 리뷰")
    for i, row in enumerate(top_neg.itertuples(), 1):
        lines.append(f"{i}. ({row.sentiment['score']:.3f}) {row.text}")

    # ─── 여기부터 요청사항만 바꿨습니다 ───
    lines += [
        "\n위 리뷰를 참고하여, 소비자 관점에서 아래 내용을 응답해 주세요:",
        "1. **추천 메뉴**",
        "2. **낮은 평점에서 자주 언급된 식당의 문제점**",
        "3. **해시태그**",
    ]
    return "\n".join(lines)


# --- 분석 함수들 정의 끝 ---