import streamlit as st
import pandas as pd
import openai
from datetime import datetime, timedelta, date
import json
import re
from typing import Dict, List, Tuple
import base64
from io import BytesIO
import numpy as np
import sqlite3
import pickle
from pathlib import Path
import hashlib # ハッシュ生成用にインポート
from dotenv import load_dotenv # 追加
import os # 追加

# .envファイルをロード
load_dotenv()

# --- Streamlitアプリのスタイル設定 ---
# アプリ全体の背景を白、文字を黒に設定
st.markdown(
    """
    <style>
    body {
        background-color: white !important;
        color: black !important;
    }
    .stApp {
        background-color: white !important;
        color: black !important;
    }
    /* Streamlitウィジェットの見た目をさらに調整 */
    h1, h2, h3, h4, h5, h6, strong, p, div, span, label {
        color: black !important;
    }
    div[data-testid="stSidebar"] {
        background-color: #f0f0f0 !important; /* サイドバーの背景を少し薄いグレーに (好みで調整) */
        color: black !important;
    }
    .stTextInput label, .stTextArea label, .stSelectbox label {
        color: black !important;
    }
    textarea {
        background-color: white !important;
        color: black !important;
        border: 1px solid #ccc !important;
        border-radius: 5px !important;
        padding: 10px !important;
    }
    textarea[disabled] { /* 読み取り専用のテキストエリアのスタイル */
        background-color: #f9f9f9 !important;
        color: #555 !important;
        opacity: 0.8 !important;
    }
    input[type="text"] {
        background-color: white !important;
        color: black !important;
        border: 1px solid #ccc !important;
        border-radius: 5px !important;
        padding: 10px !important;
    }
    /* ボタンのスタイル */
    button {
        background-color: #007bff !important;
        color: white !important;
        border-radius: 5px !important;
        padding: 8px 15px !important;
        transition: background-color 0.2s !important;
        border: none !important;
    }
    button:hover {
        background-color: #0056b3 !important;
    }
    button[data-testid="stFormSubmitButton"] {
        background-color: #28a745 !important;
    }
    button[data-testid="stFormSubmitButton"]:hover {
        background-color: #218838 !important;
    }
    /* 成功メッセージの色 */
    div[data-testid="stAlert"] div[role="alert"].streamlit-success {
        background-color: #d4edda !important;
        color: #155724 !important;
        border-color: #c3e6cb !important;
    }
    /* 警告メッセージの色 */
    div[data-testid="stAlert"] div[role="alert"].streamlit-warning {
        background-color: #fff3cd !important;
        color: #856404 !important;
        border-color: #ffeeba !important;
    }
    /* エラーメッセージの色 */
    div[data-testid="stAlert"] div[role="alert"].streamlit-error {
        background-color: #f8d7da !important;
        color: #721c24 !important;
        border-color: #f5c6cb !important;
    }
    .css-1ht1j8x { /* メトリックの背景を白に */
        background-color: white !important;
        border-radius: 0.5rem;
        padding: 1rem;
        box-shadow: 0 0.125rem 0.25rem rgba(0, 0, 0, 0.075) !important;
        border: 1px solid #e0e0e0;
    }
    </style>
    """,
    unsafe_allow_html=True
)
# --- スタイル設定ここまで ---

# ページ設定
st.set_page_config(
    page_title="アパレル店舗週次レポート作成システム",
    page_icon="🏪",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- データベース設定とヘルパー関数 ---
DB_PATH = 'apparel_reports.db' # データベースファイル名変更

class DBManager:
    """データベース接続と操作を管理するクラス"""
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self):
        """データベース接続を確立し、Rowファクトリを設定します。"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row # カラム名でアクセスできるようにする
        return conn

    def _init_db(self):
        """データベースとテーブルを初期化します。指定された店舗名のみを登録します。"""
        conn = self._get_connection()
        with conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS stores (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE
                );
            ''')
            conn.execute('''
                CREATE TABLE IF NOT EXISTS weekly_reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    store_id INTEGER NOT NULL,
                    monday_date TEXT NOT NULL, -- YYYY-MM-DD形式
                    
                    daily_reports_json TEXT,    -- 各曜日の動向と要因をJSON文字列で保存
                    topics TEXT,
                    impact_day TEXT,
                    quantitative_data TEXT,
                    
                    generated_report_json TEXT, -- AI生成レポート（動向、要因、質問）をJSONで保存
                    modified_report_json TEXT,  -- 修正後のレポート（動向、要因、修正理由など）をJSONで保存
                    
                    timestamp TEXT,             -- 作成/最終更新日時
                    FOREIGN KEY (store_id) REFERENCES stores(id),
                    UNIQUE(store_id, monday_date)
                );
            ''')
            
            conn.execute('''
                CREATE TABLE IF NOT EXISTS learning_patterns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    input_context_hash TEXT NOT NULL UNIQUE, -- 入力コンテキストのハッシュ値
                    original_output_json TEXT,
                    modified_output_json TEXT,
                    edit_reason TEXT,
                    usage_count INTEGER DEFAULT 1,
                    last_used TEXT
                )
            ''')
            
            # 指定された店舗名のみを挿入 (既に存在する場合はスキップ)
            for store_name in ['RAY', 'RSJ', 'ROS', 'RNG']:
                conn.execute("INSERT OR IGNORE INTO stores (name) VALUES (?)", (store_name,))
            conn.commit()
        conn.close()

    def get_store_id_by_name(self, store_name: str) -> int:
        """ストア名からIDを取得します。"""
        conn = self._get_connection()
        store_id = conn.execute('SELECT id FROM stores WHERE name = ?', (store_name,)).fetchone()['id']
        conn.close()
        return store_id

    def get_store_name_by_id(self, store_id: int) -> str:
        """ストアIDから名前を取得します。"""
        conn = self._get_connection()
        store_name = conn.execute('SELECT name FROM stores WHERE id = ?', (store_id,)).fetchone()['id']
        conn.close()
        return store_name
    
    def get_all_stores(self) -> List[Tuple[int, str]]:
        """全ての店舗のIDと名前を取得します。"""
        conn = self._get_connection()
        stores = conn.execute('SELECT id, name FROM stores ORDER BY name').fetchall()
        conn.close()
        return [(s['id'], s['name']) for s in stores]

    def save_weekly_data(self, store_id: int, monday_date_str: str, data: Dict, original_report: Dict, modified_report: Dict = None):
        """週次データをDBに保存または更新します。"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        daily_reports_json = json.dumps(data['daily_reports'], ensure_ascii=False)
        generated_report_json = json.dumps(original_report, ensure_ascii=False)
        modified_report_json = json.dumps(modified_report, ensure_ascii=False) if modified_report else None
        
        cursor.execute(
            'SELECT id FROM weekly_reports WHERE store_id = ? AND monday_date = ?',
            (store_id, monday_date_str)
        )
        existing_record = cursor.fetchone()

        if existing_record:
            cursor.execute('''
                UPDATE weekly_reports SET
                   daily_reports_json = ?, topics = ?, impact_day = ?,
                   quantitative_data = ?, generated_report_json = ?,
                   modified_report_json = ?, timestamp = ?
                WHERE id = ?
            ''', (
                daily_reports_json,
                data.get('topics', ''),
                data.get('impact_day', ''),
                data.get('quantitative_data', ''),
                generated_report_json,
                modified_report_json,
                datetime.now().isoformat(),
                existing_record['id']
            ))
        else:
            cursor.execute('''
                INSERT INTO weekly_reports 
                (store_id, monday_date, daily_reports_json, topics, impact_day, 
                 quantitative_data, generated_report_json, modified_report_json, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                store_id,
                monday_date_str,
                daily_reports_json,
                data.get('topics', ''),
                data.get('impact_day', ''),
                data.get('quantitative_data', ''),
                generated_report_json,
                modified_report_json,
                datetime.now().isoformat()
            ))
        
        conn.commit()
        conn.close()
        return existing_record is not None

    def get_weekly_report(self, store_id: int, monday_date_str: str) -> Dict:
        """指定された週のレポートデータを取得します。"""
        conn = self._get_connection()
        report_row = conn.execute(
            'SELECT * FROM weekly_reports WHERE store_id = ? AND monday_date = ?',
            (store_id, monday_date_str)
        ).fetchone()
        conn.close()

        if report_row:
            report_data = dict(report_row) # Rowオブジェクトを辞書に変換
            report_data['daily_reports'] = json.loads(report_data['daily_reports_json']) if report_data['daily_reports_json'] else {}
            report_data['generated_report'] = json.loads(report_data['generated_report_json']) if report_data['generated_report_json'] else {}
            report_data['modified_report'] = json.loads(report_data['modified_report_json']) if report_data['modified_report_json'] else None
            
            del report_data['daily_reports_json']
            del report_data['generated_report_json']
            if 'modified_report_json' in report_data:
                del report_data['modified_report_json']

            return report_data
        return {}
    
    def get_all_weekly_reports(self, store_id: int = None) -> List[Dict]:
        """全ての週次レポート、または指定した店舗の週次レポートを取得します。"""
        conn = self._get_connection()
        if store_id:
            reports_rows = conn.execute(
                'SELECT id, store_id, monday_date, timestamp, generated_report_json, modified_report_json '
                'FROM weekly_reports WHERE store_id = ? ORDER BY monday_date DESC', (store_id,)
            ).fetchall()
        else:
            reports_rows = conn.execute(
                'SELECT id, store_id, monday_date, timestamp, generated_report_json, modified_report_json '
                'FROM weekly_reports ORDER BY monday_date DESC'
            ).fetchall()
        conn.close()

        reports = []
        for row in reports_rows:
            report_data = dict(row)
            report_data['store_name'] = self.get_store_name_by_id(report_data['store_id'])
            
            # 生成レポートと修正レポートの有無をフラグとして追加
            report_data['has_generated'] = report_data['generated_report_json'] is not None
            report_data['has_modified'] = report_data['modified_report_json'] is not None

            # JSON文字列は生データとして保持し、必要に応じてパースする
            reports.append(report_data)
        return reports

    def find_similar_cases(self, current_data: Dict) -> str:
        """類似ケースを検索し、LLMに渡すためのコンテキストを生成します。"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT daily_reports_json, modified_report_json 
            FROM weekly_reports 
            WHERE modified_report_json IS NOT NULL
            ORDER BY timestamp DESC
            LIMIT 5
        ''') 
        
        results = cursor.fetchall()
        conn.close()
        
        similar_cases_context = []
        for result in results:
            try:
                past_modified_report = json.loads(result[1])
                
                context_item = (
                    f"- 過去の類似ケース (修正後): {past_modified_report.get('trend', '')[:100]}...\n"
                    f"  要因: {', '.join(past_modified_report.get('factors', []))}\n"
                    f"  (修正理由: {past_modified_report.get('edit_reason', '不明')[:50]}...)\n"
                )
                similar_cases_context.append(context_item)

            except json.JSONDecodeError:
                continue
        
        if similar_cases_context:
            return "\n【過去の修正済みレポート例】\n" + "\n".join(similar_cases_context)
        return ""
    
    def get_learning_stats(self) -> Dict:
        """学習に関する統計情報を取得します。"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        total_reports = cursor.execute("SELECT COUNT(*) FROM weekly_reports").fetchone()[0]
        corrections = cursor.execute("SELECT COUNT(*) FROM weekly_reports WHERE modified_report_json IS NOT NULL").fetchone()[0]
        total_patterns = cursor.execute("SELECT COUNT(*) FROM learning_patterns").fetchone()[0]
        
        conn.close()
        
        return {
            'total_reports': total_reports,
            'corrections': corrections,
            'patterns': total_patterns
        }

class ApparelReportGenerator:
    def __init__(self):
        self.openai_client = None
        self.training_data = None 
        self.memory_db = None 
        self.learning_engine = None
        
    def set_dependencies(self, memory_db_instance, learning_engine_instance):
        """外部から依存関係を設定するためのメソッド"""
        self.memory_db = memory_db_instance
        self.learning_engine = learning_engine_instance

    def initialize_openai(self, api_key: str):
        """OpenAI APIクライアントを初期化"""
        try:
            # ここをopenai.OpenAI()に修正 (バージョン1.0以降の記法)
            self.openai_client = openai.OpenAI(api_key=api_key) 
            return True
        except Exception as e:
            st.error(f"OpenAI API初期化エラー: {str(e)}")
            return False
        
    def load_training_data(self, csv_file_path):
        """ファインチューニング用CSVデータを読み込み"""
        try:
            self.training_data = pd.read_csv(csv_file_path)
            return True
        except Exception as e:
            st.error(f"学習データ読み込みエラー: {str(e)}")
            return False
    
    
    def analyze_trend_factors(self, daily_reports: Dict, topics: str, impact_day: str, quantitative_data: str) -> Dict:
        """日次レポートを分析し、動向と要因を抽出"""
        
        current_data_for_context = {
            'daily_reports': daily_reports,
            'topics': topics,
            'impact_day': impact_day,
            'quantitative_data': quantitative_data
        }
        enhanced_context = ""
        if self.memory_db and self.learning_engine:
             enhanced_context = self.memory_db.find_similar_cases(current_data_for_context) # find_similar_casesを使用
        
        system_prompt = self._build_system_prompt()
        # 修正: _build_user_prompt に渡す daily_reports は、すでに選択されたストアのみのデータになっている
        user_prompt = self._build_user_prompt(daily_reports, topics, impact_day, quantitative_data, enhanced_context) 
        
        if not self.openai_client:
            st.error("OpenAIクライアントが初期化されていません。APIキーを確認してください。")
            return None
        try:
            # 修正: openai.ChatCompletion.create を self.openai_client.chat.completions.create に変更
            response = self.openai_client.chat.completions.create( 
                model="gpt-4o-mini", # 使用するモデル
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3, # 生成の多様性を調整 (低めにして安定性を優先)
                max_tokens=1000 # 最大トークン数を調整 (出力形式に合わせて)
            )
            
            result = response.choices[0].message.content
            return self._parse_analysis_result(result)
            
        except openai.APIStatusError as e: # ここはopenaiモジュールレベルのエラークラスでOK
            if e.status_code == 401: # 認証エラー (Unauthorized)
                st.error("OpenAI APIキーが無効です。設定ページでAPIキーを正しく入力してください。")
            elif e.status_code == 429: # レート制限エラー (Too Many Requests)
                st.error("OpenAI APIのリクエストがレート制限を超えました。しばらく待ってから再試行してください。")
            else:
                st.error(f"OpenAI APIエラー: {e.status_code} - {e.response}")
            return None
        except openai.APITimeoutError: # タイムアウトエラー
            st.error("OpenAI APIへのリクエストがタイムアウトしました。ネットワーク接続を確認し、再試行してください。")
            return None
        except Exception as e:
            st.error(f"AI分析エラー: {str(e)}")
            return None
        
    
    def _build_system_prompt(self) -> str:
        """システムプロンプトを構築"""
        base_prompt = """
        あなたはアパレル小売業界の専門アナリストです。
        与えられた日次レポートデータ、TOPICS、インパクト大、定量データを基に、週次レポートを作成してください。

        【分析要件】
        1.  動向と要因の因果関係を明確に記述すること。
        2.  「目論見以下」などの結果表現は、具体的な要因まで深掘りして説明すること。
        3.  提供された定量データとの整合性を確認し、レポートに反映させること。
        4.  TOPICSやインパクト大の事象が週全体に与えた影響度を評価し、レポートに含めること。
        5.  簡潔で、アパレル店舗の上位部署が理解しやすい表現を用いること。
        6.  週全体の動向として、**指定された店舗の情報を中心に**分析すること。（他の店舗の情報は参考程度にとどめる）

        【出力形式】
        必ず以下のJSON形式で出力してください。
        ```json
        {
            "trend": "週全体の動向を400字程度で記述。各店舗の動向と要因、定量データ、TOPICS、インパクト大を統合し、因果関係を重視して説明する。",
            "factors": [
                "最も影響の大きかった要因1 (30字以内)",
                "次に影響の大きかった要因2 (30字以内)",
                "3番目に影響の大きかった要因3 (30字以内)"
            ],
            "questions": [
                "不明点や追加確認が必要な項目があれば、簡潔な質問形式で記述。なければ空の配列。"
            ]
        }
        ```
        - 「trend」は400字程度を厳守すること。
        - 「factors」は最大3つまでとし、それぞれ30字以内とすること。
        - JSON形式以外での出力は厳禁です。
        """
        
        if self.training_data is not None and not self.training_data.empty:
            training_context = self._extract_training_context()
            if training_context:
                base_prompt += f"\n\n【社内用語・文体・過去の類似例の参考情報】\n{training_context}"
        
        return base_prompt
    
    def _build_user_prompt(self, daily_reports: Dict, topics: str, impact_day: str, quantitative_data: str, enhanced_context: str) -> str:
        """ユーザープロンプトを構築"""
        prompt = "以下の情報から週次レポートをJSON形式で作成してください。\n\n"
        
        # 修正: daily_reports は既に単一店舗のデータになっていることを想定
        prompt += "【日次レポートデータ】\n"
        # daily_reports は { '店舗名': { '日付': { 'trend': '', 'factors': [] } } } の形式で来ると想定
        for store, data in daily_reports.items(): # このループは一度しか回らないはず
            prompt += f"- **{store}店**:\n"
            for date, report in data.items():
                trend_text = report['trend'] if report['trend'] else "未入力"
                factors_text = ", ".join(report['factors']) if report['factors'] else "なし"
                prompt += f"  - {date}: 動向={trend_text}, 要因={factors_text}\n"
        
        if topics:
            prompt += f"\n【TOPICS】\n{topics}\n"
        
        if impact_day:
            prompt += f"\n【インパクト大】\n{impact_day}\n"
        
        if quantitative_data:
            prompt += f"\n【定量データ】\n{quantitative_data}\n"
        
        if enhanced_context:
            prompt += f"\n{enhanced_context}\n" 
        
        return prompt
    
    def _extract_training_context(self) -> str:
        """学習データから社内用語・文体を抽出 (簡略化された例)"""
        if self.training_data is None or self.training_data.empty:
            return ""
        
        context = []
        
        if 'example_trend' in self.training_data.columns and not self.training_data['example_trend'].empty:
            context.append("過去のレポート記述例 (動向):")
            for ex in self.training_data['example_trend'].dropna().head(3):
                context.append(f"- {ex[:50]}...")
        
        if 'example_factors' in self.training_data.columns and not self.training_data['example_factors'].empty:
            context.append("過去のレポート記述例 (要因):")
            for ex in self.training_data['example_factors'].dropna().head(3):
                context.append(f"- {ex[:30]}...")
        
        return "\n".join(context)
    
    def _parse_analysis_result(self, result: str) -> Dict:
        """分析結果（JSON文字列）をパース"""
        parsed = {
            'trend': '',
            'factors': [],
            'questions': [],
            'original_result_raw': result # LLMの生の出力を保持
        }
        
        json_match = re.search(r'```json\s*(\{.*?\})\s*```', result, re.DOTALL)
        if not json_match:
            try:
                json_data = json.loads(result)
            except json.JSONDecodeError:
                st.error("AIからの出力が有効なJSON形式ではありませんでした。開発者向け情報: \n" + result)
                return parsed
        else:
            try:
                json_string = json_match.group(1)
                json_data = json.loads(json_string)
            except json.JSONDecodeError:
                st.error("AIからのJSON出力のパースに失敗しました。開発者向け情報: \n" + json_string)
                return parsed

        parsed['trend'] = json_data.get('trend', '').strip()
        parsed['factors'] = [f.strip() for f in json_data.get('factors', []) if f.strip()][:3]
        parsed['questions'] = [q.strip() for q in json_data.get('questions', []) if q.strip()]
        
        return parsed

class LearningEngine:
    """学習エンジンクラス。ユーザーの修正から学習パターンを生成・管理します。"""
    
    def __init__(self, db_manager: DBManager):
        self.db_manager = db_manager
    
    def learn_from_correction(self, input_data: Dict, original_output: Dict, modified_output: Dict):
        """ユーザーの修正から学習パターンを生成し、DBに保存します。"""
        # 入力コンテキストのハッシュを生成（簡易的な方法）
        input_context_str = json.dumps(input_data, ensure_ascii=False, sort_keys=True)
        input_context_hash = hashlib.sha256(input_context_str.encode('utf-8')).hexdigest()
        
        conn = self.db_manager._get_connection() # DBManagerから接続を取得
        cursor = conn.cursor()

        original_output_json = json.dumps(original_output, ensure_ascii=False)
        modified_output_json = json.dumps(modified_output, ensure_ascii=False)
        edit_reason = modified_output.get('edit_reason', '')

        cursor.execute('''
            SELECT id, usage_count FROM learning_patterns 
            WHERE input_context_hash = ? AND modified_output_json = ?
        ''', (input_context_hash, modified_output_json))
        
        existing_pattern = cursor.fetchone()

        if existing_pattern:
            pattern_id, usage_count = existing_pattern
            cursor.execute('''
                UPDATE learning_patterns 
                SET usage_count = ?, last_used = ?
                WHERE id = ?
            ''', (usage_count + 1, datetime.now().isoformat(), pattern_id))
            st.info("既存の学習パターンを更新しました。")
        else:
            cursor.execute('''
                INSERT INTO learning_patterns 
                (input_context_hash, original_output_json, modified_output_json, edit_reason, usage_count, last_used)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                input_context_hash,
                original_output_json,
                modified_output_json,
                edit_reason,
                1,
                datetime.now().isoformat()
            ))
            st.success("新しい学習パターンを保存しました！AIの精度向上に役立ちます。")
        
        conn.commit()
        conn.close()


# --- Streamlit UI Components ---

def get_base64_of_bin_file(bin_file):
    with open(bin_file, 'rb') as f:
        data = f.read()
    return base64.b64encode(data).decode()

def get_file_download_link(df, filename, text):
    """Generates a link for downloading a pandas DataFrame as CSV."""
    csv = df.to_csv(index=False, encoding='utf-8-sig') # UTF-8 BOM付きでExcel対応
    b64 = base64.b64encode(csv.encode()).decode()
    href = f'<a href="data:file/csv;base64,{b64}" download="{filename}">{text}</a>'
    return href

def get_excel_download_link(df, filename, text):
    """Generates a link for downloading a pandas DataFrame as Excel."""
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='レポート')
    b64 = base64.b64encode(output.getvalue()).decode()
    href = f'<a href="data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64,{b64}" download="{filename}">{text}</a>'
    return href

# グローバルインスタンスの初期化
db_manager = DBManager()
report_generator = ApparelReportGenerator()
learning_engine = LearningEngine(db_manager)

# 依存関係を設定
report_generator.set_dependencies(db_manager, learning_engine)

# ★ここから追加するコード★
TRAINING_CSV_FILE = "training_data.csv" # ここを実際のファイル名に置き換えてください！

if Path(TRAINING_CSV_FILE).exists():
    if report_generator.load_training_data(TRAINING_CSV_FILE):
        st.sidebar.success(f"学習データ '{TRAINING_CSV_FILE}' を読み込みました。")
    else:
        st.sidebar.warning(f"学習データ '{TRAINING_CSV_FILE}' の読み込みに失敗しました。ファイルの内容を確認してください。")
else:
    st.sidebar.info(f"学習データ '{TRAINING_CSV_FILE}' が見つかりませんでした。学習機能は無効になります。")
# ★ここまで追加するコード★

def get_monday_of_week(selected_date: date) -> date:
    """与えられた日付が属する週の月曜日を計算します。"""
    # 選択された日付の曜日を取得 (月曜日=0, 日曜日=6)
    weekday = selected_date.weekday()
    # 月曜日に戻るための日数を計算
    days_since_monday = weekday
    monday = selected_date - timedelta(days=days_since_monday)
    return monday

def get_current_week_monday() -> date:
    """現在の週の月曜日を取得します。"""
    today = date.today()
    return get_monday_of_week(today)

# --- Streamlit UI Components ---

def show_report_creation_page():
    st.title("📈 週次レポート作成")
    st.markdown("---")

    st.info("このページでは、店舗ごとの日次データを入力し、AIが週次レポートを生成します。AIレポートは後で修正し、システムに学習させることができます。")

    # 週の選択
    st.header("1. レポート対象週の選択")
    # 今週の月曜日をデフォルト値にする
    default_monday = get_current_week_monday()
    selected_date = st.date_input(
        "レポートを作成する週の**月曜日**を選択してください。",
        value=default_monday,
        min_value=date(2023, 1, 1),
        max_value=date.today() + timedelta(days=30), # 未来の日付も少し許容
        format="YYYY/MM/DD"
    )
    
    # 選択された日付が月曜日であることを確認し、そうでない場合は月曜日に補正
    if selected_date.weekday() != 0:
        st.warning(f"選択された日付は月曜日ではありません。自動的に**{get_monday_of_week(selected_date).strftime('%Y年%m月%d日')}**の週として処理します。")
        monday_of_week = get_monday_of_week(selected_date)
    else:
        monday_of_week = selected_date
    
    st.session_state['selected_monday'] = monday_of_week.strftime('%Y-%m-%d')
    st.subheader(f"選択週: {monday_of_week.strftime('%Y年%m月%d日')} 〜 {(monday_of_week + timedelta(days=6)).strftime('%Y年%m月%d日')}")
    st.markdown("---")

    # 既存レポートのロード
    store_names = [s[1] for s in db_manager.get_all_stores()]
    if 'selected_store_for_report' not in st.session_state:
        st.session_state['selected_store_for_report'] = store_names[0] # デフォルトで最初の店舗

    # レポートデータ構造の初期化
    if 'daily_reports_input' not in st.session_state:
        st.session_state['daily_reports_input'] = {store_name: {} for store_name in store_names}
    if 'topics_input' not in st.session_state:
        st.session_state['topics_input'] = ""
    if 'impact_day_input' not in st.session_state:
        st.session_state['impact_day_input'] = ""
    if 'quantitative_data_input' not in st.session_state:
        st.session_state['quantitative_data_input'] = ""
    if 'generated_report_output' not in st.session_state:
        st.session_state['generated_report_output'] = None
    if 'modified_report_output' not in st.session_state:
        st.session_state['modified_report_output'] = None
    if 'report_id_to_edit' not in st.session_state:
        st.session_state['report_id_to_edit'] = None

    # 選択された週の既存レポートをロード
    # まず、ストア選択タブの現在のインデックスをセッションステートに保持
    if 'active_tab_index' not in st.session_state:
        st.session_state['active_tab_index'] = 0 # デフォルトは最初のタブ (RAY)

    # 既存レポートをロードする前に、現在選択されている店舗名を取得
    # 初期表示時や日付変更時に、選択店舗のレポートが読み込まれるように調整
    # ただし、タブのインデックスが変更された場合は、そのタブの店舗名に追従
    # ここでは、`selected_store_for_report` と `active_tab_index` の同期を強化
    
    # ロード時に、もし既存レポートが存在すれば、その店舗をデフォルトのタブにするためのインデックスを設定
    current_store_id_for_load = db_manager.get_store_id_by_name(st.session_state['selected_store_for_report'])
    existing_report = db_manager.get_weekly_report(current_store_id_for_load, st.session_state['selected_monday'])

    if existing_report:
        st.info(f"**{st.session_state['selected_store_for_report']}店**のこの週のレポートが読み込まれました。")
        st.session_state['daily_reports_input'][st.session_state['selected_store_for_report']] = existing_report['daily_reports']
        st.session_state['topics_input'] = existing_report['topics']
        st.session_state['impact_day_input'] = existing_report['impact_day']
        st.session_state['quantitative_data_input'] = existing_report['quantitative_data']
        st.session_state['generated_report_output'] = existing_report['generated_report']
        st.session_state['modified_report_output'] = existing_report['modified_report']
        st.session_state['report_id_to_edit'] = existing_report['id']
        # 既存レポートの店舗に合わせてタブを切り替える
        if st.session_state['selected_store_for_report'] in store_names:
            st.session_state['active_tab_index'] = store_names.index(st.session_state['selected_store_for_report'])
    else:
        # 新規作成の場合、既存の入力はクリアしない（日付切り替え時のデータ残存を防ぐため）
        # ただし、選択週を変更した場合は各入力フィールドの値をリセット
        if 'last_selected_monday' not in st.session_state or st.session_state['last_selected_monday'] != st.session_state['selected_monday']:
            # 全店舗のdaily_reports_inputを初期化
            for store_name in store_names:
                st.session_state['daily_reports_input'][store_name] = {
                    (monday_of_week + timedelta(days=i)).strftime('%Y-%m-%d'): {"trend": "", "factors": []} for i in range(7)
                }
            st.session_state['topics_input'] = ""
            st.session_state['impact_day_input'] = ""
            st.session_state['quantitative_data_input'] = ""
            st.session_state['generated_report_output'] = None
            st.session_state['modified_report_output'] = None
            st.session_state['report_id_to_edit'] = None
        st.session_state['last_selected_monday'] = st.session_state['selected_monday']

    st.header("2. 日次レポートデータの入力")
    st.markdown("各店舗の**日ごとの動向と要因**を入力してください。要因は複数入力可能です（カンマ区切り）。")
    
    # 店舗ごとのタブ表示（色が変わるように修正）
    # `st.tabs` の戻り値をセッションステートに保存し、現在選択されているタブのインデックスとして利用
    # TypeError: LayoutsMixin.tabs() got an unexpected keyword argument 'key' エラー対応: keyを削除
    tabs = st.tabs(
        store_names
    )

    # 現在選択されているタブのインデックス (st.tabs() は最後に選択されたタブのインデックスを返す)
    # これをセッションステートに保存することで、UIと内部状態を同期させる
    # Streamlitの動作では、タブがクリックされると、次にスクリプトが再実行されるときに
    # st.tabs() がその新しいインデックスを返す
    
    # ここで `tabs` 変数 (st.tabs() の戻り値であるタブオブジェクトのリスト) を使用して、
    # 各タブのコンテンツを表示する
    for i, tab in enumerate(tabs):
        with tab:
            current_store_name_for_input = store_names[i] # このタブに対応する店舗名
            st.session_state['selected_store_for_report'] = current_store_name_for_input # セッションステートの選択店舗名を更新

            # このタブが選択されている場合にのみ、その店舗の入力フィールドを表示
            # st.tabs() の挙動により、with tab: のブロックに入った時点で、そのタブがアクティブになっている
            # なので、追加の if st.session_state['active_tab_index'] == i: は不要
            
            # まず、現在の店舗のdaily_reports_inputを確実に初期化
            if current_store_name_for_input not in st.session_state['daily_reports_input']:
                st.session_state['daily_reports_input'][current_store_name_for_input] = {
                    (monday_of_week + timedelta(days=j)).strftime('%Y-%m-%d'): {"trend": "", "factors": []} for j in range(7)
                }

            # 選択された店舗の日次レポート入力欄を表示
            for j in range(7): # 月曜日から日曜日まで
                current_date = monday_of_week + timedelta(days=j)
                date_str = current_date.strftime('%Y-%m-%d')
                day_name = ["月", "火", "水", "木", "金", "土", "日"][j]

                st.subheader(f"🗓️ {current_date.strftime('%Y年%m月%d日')} ({day_name})")
                
                # 日次動向
                st.session_state['daily_reports_input'][current_store_name_for_input][date_str]['trend'] = st.text_area(
                    f"{day_name}曜日の動向（{current_store_name_for_input}店）",
                    value=st.session_state['daily_reports_input'][current_store_name_for_input].get(date_str, {}).get('trend', ''),
                    height=100,
                    key=f"trend_{current_store_name_for_input}_{date_str}"
                )
                
                # 日次要因
                # リストをカンマ区切り文字列に変換して表示
                factors_str = ", ".join(st.session_state['daily_reports_input'][current_store_name_for_input].get(date_str, {}).get('factors', []))
                edited_factors_str = st.text_input(
                    f"{day_name}曜日の要因（複数ある場合はカンマ区切り、{current_store_name_for_input}店）",
                    value=factors_str,
                    key=f"factors_{current_store_name_for_input}_{date_str}"
                )
                # ユーザーが入力した文字列をリストに変換して保存
                st.session_state['daily_reports_input'][current_store_name_for_input][date_str]['factors'] = [f.strip() for f in edited_factors_str.split(',') if f.strip()]
                st.markdown("---")

    st.header("3. 週全体の補足情報の入力")
    st.markdown("週全体にわたる重要なトピックス、特に影響の大きかった日、および定量データを入力してください。")

    st.text_area(
    "今日のトピック（例: 売上向上策、顧客満足度向上、新商品開発）",
    height=100, # 68px以上であればOK
    key='topics_input',
    value=st.session_state.get('topics_input', '') # この value は初回表示時の初期値として機能
    )
    st.text_area(
    "翌日以降のインパクト（翌日以降に影響する要因を具体的に記入）",
    height=100, # ここは68px以上であることを確認してください
    key='impact_day_input',
    value=st.session_state.get('impact_day_input', '')
    )
    st.text_area(
    "定量データ（例: 売上高、客数、客単価、ロス率など具体的な数値）",
    height=100, # ここは68px以上であることを確認してください
    key='quantitative_data_input',
    value=st.session_state.get('quantitative_data_input', '')
    )
    st.markdown("---")

    st.header("4. 週次レポートの生成")
    if st.button("AIに週次レポートを生成させる", type="primary"):
        with st.spinner("AIがレポートを生成中です...しばらくお待ちください。"):
            # 選択中の店舗の日次レポートのみを抽出
            selected_store_daily_report = {
                st.session_state['selected_store_for_report']: st.session_state['daily_reports_input'][st.session_state['selected_store_for_report']]
            }

            generated_report = report_generator.analyze_trend_factors(
                daily_reports=selected_store_daily_report, # 選択された店舗の日次レポートのみを渡す
                topics=st.session_state['topics_input'],
                impact_day=st.session_state['impact_day_input'],
                quantitative_data=st.session_state['quantitative_data_input']
            )

            if generated_report:
                st.session_state['generated_report_output'] = generated_report
                st.session_state['modified_report_output'] = None # 新規生成時は修正版をリセット
                st.success("レポートが生成されました！内容を確認し、必要に応じて修正してください。")
            else:
                st.error("レポートの生成に失敗しました。入力内容を確認するか、再度お試しください。")
    
    if st.session_state['generated_report_output']:
        st.subheader("📝 生成された週次レポート (AI生成)")
        
        # AI生成レポートの表示
        trend_ai = st.session_state['generated_report_output'].get('trend', '')
        factors_ai = st.session_state['generated_report_output'].get('factors', [])
        questions_ai = st.session_state['generated_report_output'].get('questions', [])

        st.text_area("動向", value=trend_ai, height=200, disabled=True, key="ai_trend")
        st.text_area("要因", value="\n".join(factors_ai), height=80, disabled=True, key="ai_factors")
        st.text_area("質問事項", value="\n".join(questions_ai) if questions_ai else "なし", height=80, disabled=True, key="ai_questions")
        
        st.markdown("---")
        st.header("5. 生成されたレポートの修正と保存 (任意)")
        st.warning("AIが生成したレポートは、必要に応じて修正し、学習データとしてシステムに保存できます。")

        # 修正フォーム
        with st.form("modify_report_form"):
            modified_trend = st.text_area("動向 (修正)", value=st.session_state['modified_report_output'].get('trend', trend_ai) if st.session_state['modified_report_output'] else trend_ai, height=200)
            modified_factors_str = st.text_area("要因 (修正、カンマ区切り)", value=", ".join(st.session_state['modified_report_output'].get('factors', factors_ai)) if st.session_state['modified_report_output'] else ", ".join(factors_ai), height=80)
            modified_questions_str = st.text_area("質問事項 (修正、カンマ区切り)", value=", ".join(st.session_state['modified_report_output'].get('questions', questions_ai)) if st.session_state['modified_report_output'] else ", ".join(questions_ai), height=80)
            edit_reason = st.text_area("修正理由（AIの学習に利用されます）", value=st.session_state['modified_report_output'].get('edit_reason', '') if st.session_state['modified_report_output'] else '', height=100)

            submitted = st.form_submit_button("修正内容を保存し、AIに学習させる")
            if submitted:
                # 修正後の要因と質問事項をリストに変換
                modified_factors = [f.strip() for f in modified_factors_str.split(',') if f.strip()]
                modified_questions = [q.strip() for q in modified_questions_str.split(',') if q.strip()]

                modified_report = {
                    "trend": modified_trend,
                    "factors": modified_factors,
                    "questions": modified_questions,
                    "edit_reason": edit_reason
                }
                st.session_state['modified_report_output'] = modified_report

                # レポートをDBに保存
                store_id = db_manager.get_store_id_by_name(st.session_state['selected_store_for_report'])
                input_data_for_learning = {
                    'daily_reports': {st.session_state['selected_store_for_report']: st.session_state['daily_reports_input'][st.session_state['selected_store_for_report']]},
                    'topics': st.session_state['topics_input'],
                    'impact_day': st.session_state['impact_day_input'],
                    'quantitative_data': st.session_state['quantitative_data_input']
                }
                
                db_manager.save_weekly_data(
                    store_id=store_id,
                    monday_date_str=st.session_state['selected_monday'],
                    data={
                        'daily_reports': st.session_state['daily_reports_input'][st.session_state['selected_store_for_report']],
                        'topics': st.session_state['topics_input'],
                        'impact_day': st.session_state['impact_day_input'],
                        'quantitative_data': st.session_state['quantitative_data_input']
                    },
                    original_report=st.session_state['generated_report_output'],
                    modified_report=modified_report
                )
                
                # 学習エンジンに修正内容を渡す
                learning_engine.learn_from_correction(
                    input_data=input_data_for_learning,
                    original_output=st.session_state['generated_report_output'],
                    modified_output=modified_report
                )
                st.success("修正内容が保存され、AIの学習に利用されました！")
                st.experimental_rerun() # 保存後にUIをリフレッシュ

        st.markdown("---")
        st.header("6. レポートのエクスポート")
        
        # エクスポートするレポートの選択
        export_option = st.radio(
            "エクスポートするレポートを選択してください:",
            ("AI生成レポート", "修正済みレポート (存在する場合)"),
            index=1 if st.session_state['modified_report_output'] else 0
        )

        report_to_export = {}
        if export_option == "修正済みレポート (存在する場合)" and st.session_state['modified_report_output']:
            report_to_export = st.session_state['modified_report_output']
            report_type_label = "修正済み"
        else:
            report_to_export = st.session_state['generated_report_output']
            report_type_label = "AI生成"

        if report_to_export:
            # プレビュー表示
            st.subheader(f"📄 {report_type_label}レポート プレビュー")
            st.write("**動向:**")
            st.markdown(report_to_export.get('trend', ''))
            st.write("**要因:**")
            for factor in report_to_export.get('factors', []):
                st.markdown(f"- {factor}")
            st.write("**質問事項:**")
            if report_to_export.get('questions'):
                for question in report_to_export.get('questions', []):
                    st.markdown(f"- {question}")
            else:
                st.markdown("なし")
            
            # ダウンロードボタン
            report_text_content = f"週次レポート（{report_type_label}）\n\n" \
                                  f"対象店舗: {st.session_state['selected_store_for_report']}店\n" \
                                  f"対象週: {monday_of_week.strftime('%Y年%m月%d日')} 〜 {(monday_of_week + timedelta(days=6)).strftime('%Y年%m%d日')}\n\n" \
                                  f"■ 動向:\n{report_to_export.get('trend', '')}\n\n" \
                                  f"■ 要因:\n" + "\n".join([f"- {f}" for f in report_to_export.get('factors', [])]) + "\n\n" \
                                  f"■ 質問事項:\n" + ("\n".join([f"- {q}" for q in report_to_export.get('questions', [])]) if report_to_export.get('questions') else "なし")
            
            # テキストファイルダウンロード
            st.download_button(
                label=f"📝 {report_type_label}レポートをテキストでダウンロード",
                data=report_text_content.encode('utf-8'),
                file_name=f"{st.session_state['selected_store_for_report']}_{monday_of_week.strftime('%Y%m%d')}_weekly_report_{report_type_label}.txt",
                mime="text/plain"
            )

            # JSONファイルダウンロード
            report_json_content = json.dumps(report_to_export, ensure_ascii=False, indent=2)
            st.download_button(
                label=f"📊 {report_type_label}レポートをJSONでダウンロード",
                data=report_json_content.encode('utf-8'),
                file_name=f"{st.session_state['selected_store_for_report']}_{monday_of_week.strftime('%Y%m%d')}_weekly_report_{report_type_label}.json",
                mime="application/json"
            )
        else:
            st.info("エクスポート可能なレポートがありません。")

def show_report_history_page():
    st.title("📚 レポート履歴")
    st.markdown("---")

    st.info("これまでに生成・保存された週次レポートの一覧を確認できます。")

    stores = db_manager.get_all_stores()
    store_names = ["全ての店舗"] + [s[1] for s in stores]
    
    selected_store_name = st.selectbox(
        "表示する店舗を選択してください:",
        store_names,
        key="history_store_select"
    )

    if selected_store_name == "全ての店舗":
        store_id_filter = None
    else:
        store_id_filter = db_manager.get_store_id_by_name(selected_store_name)
    
    all_reports = db_manager.get_all_weekly_reports(store_id=store_id_filter)

    if not all_reports:
        st.warning("表示するレポートがありません。")
        return

    # データフレーム表示
    df_data = []
    for report in all_reports:
        df_data.append({
            "ID": report['id'],
            "店舗名": report['store_name'],
            "週の開始日": report['monday_date'],
            "AI生成": "✅" if report['has_generated'] else "❌",
            "修正済み": "✅" if report['has_modified'] else "❌",
            "最終更新日時": datetime.fromisoformat(report['timestamp']).strftime('%Y/%m/%d %H:%M:%S')
        })
    
    df = pd.DataFrame(df_data)
    
    st.dataframe(df, use_container_width=True, hide_row_index=True)

    st.markdown("---")
    st.subheader("レポートの詳細表示とエクスポート")
    
    report_ids = [str(r['id']) for r in all_reports]
    selected_report_id = st.selectbox("詳細を表示・エクスポートするレポートのIDを選択してください:", report_ids)

    if selected_report_id:
        selected_report_data = next((r for r in all_reports if str(r['id']) == selected_report_id), None)
        if selected_report_data:
            st.write(f"### ID: {selected_report_data['id']} のレポート詳細")
            
            # JSON文字列をロードして表示
            generated_report_content = json.loads(selected_report_data['generated_report_json']) if selected_report_data['generated_report_json'] else None
            modified_report_content = json.loads(selected_report_data['modified_report_json']) if selected_report_data['modified_report_json'] else None
            
            # タブで表示
            report_tabs = []
            if generated_report_content:
                report_tabs.append("AI生成レポート")
            if modified_report_content:
                report_tabs.append("修正済みレポート")
            
            if not report_tabs:
                st.warning("このレポートには、AI生成または修正済みのレポートデータがありません。")
                return

            selected_report_tab = st.radio("表示するレポートタイプ:", report_tabs)

            displayed_report = {}
            report_label = ""

            if selected_report_tab == "AI生成レポート" and generated_report_content:
                displayed_report = generated_report_content
                report_label = "AI生成レポート"
            elif selected_report_tab == "修正済みレポート" and modified_report_content:
                displayed_report = modified_report_content
                report_label = "修正済みレポート"
            
            if displayed_report:
                st.write(f"#### {report_label}")
                st.write("**動向:**")
                st.markdown(displayed_report.get('trend', ''))
                st.write("**要因:**")
                for factor in displayed_report.get('factors', []):
                    st.markdown(f"- {factor}")
                st.write("**質問事項:**")
                if displayed_report.get('questions'):
                    for question in displayed_report.get('questions', []):
                        st.markdown(f"- {question}")
                else:
                    st.markdown("なし")

                if 'edit_reason' in displayed_report and displayed_report['edit_reason']:
                    st.write("**修正理由:**")
                    st.markdown(displayed_report['edit_reason'])

                # エクスポートボタン
                report_text_content = f"週次レポート（{report_label}）\n\n" \
                                      f"対象店舗: {selected_report_data['store_name']}店\n" \
                                      f"対象週: {selected_report_data['monday_date']} 〜 {(datetime.strptime(selected_report_data['monday_date'], '%Y-%m-%d').date() + timedelta(days=6)).strftime('%Y%m%d')}\n\n" \
                                      f"■ 動向:\n{displayed_report.get('trend', '')}\n\n" \
                                      f"■ 要因:\n" + "\n".join([f"- {f}" for f in displayed_report.get('factors', [])]) + "\n\n" \
                                      f"■ 質問事項:\n" + ("\n".join([f"- {q}" for q in displayed_report.get('questions', [])]) if displayed_report.get('questions') else "なし")
                
                # テキストファイルダウンロード
                st.download_button(
                    label=f"📝 {report_label}をテキストでダウンロード",
                    data=report_text_content.encode('utf-8'),
                    file_name=f"{selected_report_data['store_name']}_{selected_report_data['monday_date']}_weekly_report_{report_label}.txt",
                    mime="text/plain",
                    key=f"download_txt_{selected_report_id}_{report_label}"
                )

                # JSONファイルダウンロード
                report_json_content = json.dumps(displayed_report, ensure_ascii=False, indent=2)
                st.download_button(
                    label=f"📊 {report_label}をJSONでダウンロード",
                    data=report_json_content.encode('utf-8'),
                    file_name=f"{selected_report_data['store_name']}_{selected_report_data['monday_date']}_weekly_report_{report_label}.json",
                    mime="application/json",
                    key=f"download_json_{selected_report_id}_{report_label}"
                )

def show_learning_status_page():
    st.title("🧠 AI学習状況")
    st.markdown("---")

    st.info("このページでは、AIの学習に関する現在の統計情報を確認できます。")

    stats = db_manager.get_learning_stats()

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric(label="合計レポート数", value=stats['total_reports'])
    with col2:
        st.metric(label="修正済みレポート数 (学習済み)", value=stats['corrections'])
    with col3:
        st.metric(label="学習パターン数", value=stats['patterns'])
    
    st.markdown("---")
    st.subheader("学習パターンの詳細")
    st.info("学習パターンは、ユーザーがAI生成レポートを修正した際にシステムが自動的に記録したものです。これにより、AIはより適切なレポートを生成するよう学習します。")
    
    conn = db_manager._get_connection()
    learning_patterns_df = pd.read_sql_query("SELECT * FROM learning_patterns ORDER BY last_used DESC", conn)
    conn.close()

    if not learning_patterns_df.empty:
        # JSON文字列を展開して表示
        display_df = learning_patterns_df.copy()
        
        display_df['元の出力 (抜粋)'] = display_df['original_output_json'].apply(lambda x: json.loads(x).get('trend', '')[:50] + '...' if x else '')
        display_df['修正後の出力 (抜粋)'] = display_df['modified_output_json'].apply(lambda x: json.loads(x).get('trend', '')[:50] + '...' if x else '')
        
        st.dataframe(
            display_df[['id', 'usage_count', 'last_used', 'edit_reason', '元の出力 (抜粋)', '修正後の出力 (抜粋)']],
            use_container_width=True,
            hide_row_index=True
        )

        st.markdown("---")
        st.subheader("個別の学習パターンの詳細")
        pattern_ids = [""] + [str(pid) for pid in learning_patterns_df['id'].tolist()]
        selected_pattern_id = st.selectbox("詳細を表示する学習パターンIDを選択:", pattern_ids)

        if selected_pattern_id:
            selected_pattern = learning_patterns_df[learning_patterns_df['id'] == int(selected_pattern_id)].iloc[0]
            
            st.write(f"#### パターンID: {selected_pattern['id']}")
            st.write(f"**利用回数:** {selected_pattern['usage_count']}")
            st.write(f"**最終利用日時:** {selected_pattern['last_used']}")
            st.write(f"**修正理由:** {selected_pattern['edit_reason']}")
            
            st.markdown("---")
            st.write("##### 元のAI生成出力")
            st.json(json.loads(selected_pattern['original_output_json']))
            
            st.markdown("---")
            st.write("##### 修正後の出力")
            st.json(json.loads(selected_pattern['modified_output_json']))

    else:
        st.info("まだ学習パターンが保存されていません。レポートを修正して保存すると、ここにパターンが追加されます。")

def show_settings_page():
    st.title("⚙️ 設定")
    st.markdown("---")

    st.info("Streamlitアプリケーションの動作に必要な設定を行います。特にOpenAI APIキーは必須です。")

    st.subheader("OpenAI APIキー設定")
    openai_api_key = st.text_input(
        "OpenAI API Key (sk-から始まるキー)",
        type="password",
        value=st.session_state.get("openai_api_key", os.getenv("OPENAI_API_KEY", "")), # .envからも読み込む
        help="OpenAIのAPIキーを入力してください。これによりAIレポート生成機能が利用可能になります。"
    )

    if st.button("APIキーを保存"):
        if openai_api_key:
            st.session_state["openai_api_key"] = openai_api_key
            # 環境変数に設定 (現在のセッションのみ)
            os.environ["OPENAI_API_KEY"] = openai_api_key
            
            # レポート生成器にキーを設定
            if report_generator.initialize_openai(openai_api_key):
                st.success("OpenAI APIキーが正常に設定されました。")
            else:
                st.error("OpenAI APIキーの設定に失敗しました。キーが正しいか確認してください。")
        else:
            st.error("APIキーが入力されていません。")
    
    if "openai_api_key" in st.session_state and st.session_state["openai_api_key"]:
        st.success("APIキーが設定済みです。")
    elif os.getenv("OPENAI_API_KEY"):
        st.success("APIキーが環境変数から設定済みです。")
        # 環境変数から設定されている場合は、レポート生成器も初期化しておく
        if not report_generator.openai_client:
            report_generator.initialize_openai(os.getenv("OPENAI_API_KEY"))
    else:
        st.warning("OpenAI APIキーが設定されていません。レポート生成機能は利用できません。")

    st.markdown("---")
    st.subheader("学習データCSVファイルのアップロード")
    st.info("AIの応答スタイルや専門用語を調整するための学習データ（CSV形式）をアップロードできます。既存のCSVを基にファインチューニングを行う場合に使用します。")

    uploaded_file = st.file_uploader("学習データCSVファイルをアップロード", type=["csv"])

    if uploaded_file:
        if report_generator.load_training_data(uploaded_file):
            st.success("学習データが正常に読み込まれました。")
            st.dataframe(report_generator.training_data.head()) # 最初の5行を表示
        else:
            st.error("学習データの読み込みに失敗しました。CSVファイル形式を確認してください。")

# --- メインアプリケーションロジック ---

# サイドバーメニュー
with st.sidebar:
    st.image("https://www.streamlit.io/images/brand/streamlit-mark-color.svg", width=50)
    st.title("アパレル店舗週次レポートシステム")
    st.markdown("---")
    
    menu_options = {
        "レポート作成": show_report_creation_page,
        "レポート履歴": show_report_history_page,
        "AI学習状況": show_learning_status_page,
        "設定": show_settings_page
    }

    selected_menu = st.radio("メニュー", list(menu_options.keys()))

    st.markdown("---")
    st.write("Developed with ❤️ by Streamlit & AI")

# 選択されたメニューに応じたページを表示
if selected_menu:
    menu_options[selected_menu]()

# 初期ロード時にAPIキーが設定されていればレポートジェネレーターを初期化
if "openai_api_key" in st.session_state and st.session_state["openai_api_key"] and not report_generator.openai_client:
    report_generator.initialize_openai(st.session_state["openai_api_key"])
elif os.getenv("OPENAI_API_KEY") and not report_generator.openai_client:
    report_generator.initialize_openai(os.getenv("OPENAI_API_KEY"))