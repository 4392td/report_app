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
    /* カレンダーの背景を白に設定 */
    .react-datepicker {
        background-color: white !important;
        color: black !important; /* テキスト色も黒に */
    }
    .react-datepicker__header {
        background-color: white !important;
        color: black !important;
    }
    .react-datepicker__month-container {
        background-color: white !important;
        color: black !important;
    }
    .react-datepicker__day-name, .react-datepicker__day, .react-datepicker__time-name {
        color: black !important;
    }
    .react-datepicker__current-month {
        color: black !important;
    }
    .react-datepicker__navigation--previous, .react-datepicker__navigation--next {
        color: black !important;
    }
    /* 選択された日付の背景色を赤、文字色を白に設定 */
    .react-datepicker__day--selected,
    .react-datepicker__day--range-start,
    .react-datepicker__day--range-end,
    .react-datepicker__day--in-range {
        background-color: #ff4b4b !important; /* Streamlitのデフォルト赤色に近づける */
        color: white !important;
    }
    /* ホバー時の日付の背景色 */
    .react-datepicker__day:hover {
        background-color: #e0e0e0 !important; /* ホバー時の背景色を薄いグレーに */
        color: black !important;
    }
    /* 選択できない日付（過去や未来でmin/max_value外）の文字色 */
    .react-datepicker__day--disabled {
        color: #ccc !important;
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
                    monday_date TEXT NOT NULL, --YYYY-MM-DD形式
                    
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
        # daily_reports は { '店舗名': { '日付': { 'trend': '', 'factors': [] } } の形式で来ると想定
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
                    f"**{current_date.strftime('%m/%d')} 動向:**",
                    value=st.session_state['daily_reports_input'][current_store_name_for_input].get(date_str, {}).get('trend', ''),
                    key=f"{current_store_name_for_input}_{date_str}_trend",
                    height=80
                )
                # 日次要因
                factors_str = ", ".join(st.session_state['daily_reports_input'][current_store_name_for_input].get(date_str, {}).get('factors', []))
                new_factors_str = st.text_input(
                    f"**{current_date.strftime('%m/%d')} 要因 (カンマ区切り):**",
                    value=factors_str,
                    key=f"{current_store_name_for_input}_{date_str}_factors"
                )
                st.session_state['daily_reports_input'][current_store_name_for_input][date_str]['factors'] = [f.strip() for f in new_factors_str.split(',') if f.strip()]

    st.markdown("---")

    st.header("3. 週全体の追加情報 (任意)")
    st.session_state['topics_input'] = st.text_area(
        "**TOPICS:** 週全体を通して特筆すべき事項や出来事を入力してください。",
        value=st.session_state['topics_input'],
        height=100
    )
    st.session_state['impact_day_input'] = st.text_area(
        "**インパクト大:** 特に影響の大きかった日やイベント、その内容を記述してください。",
        value=st.session_state['impact_day_input'],
        height=100
    )
    st.session_state['quantitative_data_input'] = st.text_area(
        "**定量データ:** 売上、客数、客単価、プロパー消化率など、週の定量データを入力してください。",
        value=st.session_state['quantitative_data_input'],
        height=100
    )

    st.markdown("---")

    # AIレポート生成ボタン
    st.header("4. AIによるレポート生成")
    if st.button("AIレポートを生成", type="primary"):
        # AI生成用に整形されたデータを作成
        # daily_reports_input は全店舗のデータを持っているため、現在選択中の店舗のデータのみを渡す
        selected_store_name = st.session_state['selected_store_for_report']
        data_for_ai = {
            'daily_reports': {selected_store_name: st.session_state['daily_reports_input'][selected_store_name]},
            'topics': st.session_state['topics_input'],
            'impact_day': st.session_state['impact_day_input'],
            'quantitative_data': st.session_state['quantitative_data_input']
        }

        # APIキーの確認
        openai_api_key = os.getenv("OPENAI_API_KEY")
        if not openai_api_key:
            st.error("OpenAI APIキーが設定されていません。サイドバーの「設定」ページでAPIキーを設定してください。")
            return
        
        # OpenAIクライアントを初期化
        if not report_generator.initialize_openai(openai_api_key):
            # エラーメッセージは initialize_openai 内で表示済み
            return

        with st.spinner("AIがレポートを分析・生成中です... 少々お待ちください。"):
            generated_report = report_generator.analyze_trend_factors(
                data_for_ai['daily_reports'], # ここではすでに選択された店舗のデータのみが渡される
                data_for_ai['topics'],
                data_for_ai['impact_day'],
                data_for_ai['quantitative_data']
            )

        if generated_report:
            st.session_state['generated_report_output'] = generated_report
            st.session_state['modified_report_output'] = None # AI生成時に修正レポートはクリア
            st.success("AIレポートの生成が完了しました！")
            st.experimental_rerun() # ページを再描画して結果を表示
        else:
            st.error("AIレポートの生成に失敗しました。入力内容を確認するか、再度お試しください。")

    if st.session_state['generated_report_output']:
        st.subheader("生成された週次レポート (AI生成)")
        st.markdown("**週全体の動向と要因:**")
        st.write(st.session_state['generated_report_output'].get('trend', ''))
        st.markdown("**主な要因:**")
        for i, factor in enumerate(st.session_state['generated_report_output'].get('factors', [])):
            st.write(f"- {factor}")
        
        if st.session_state['generated_report_output'].get('questions'):
            st.markdown("**AIからの質問:**")
            for q in st.session_state['generated_report_output'].get('questions', []):
                st.write(f"- {q}")
        
        # レポート保存ボタン
        if st.button("このレポートを保存", type="secondary"):
            store_id = db_manager.get_store_id_by_name(st.session_state['selected_store_for_report'])
            monday_date_str = st.session_state['selected_monday']
            
            data_to_save = {
                'daily_reports': st.session_state['daily_reports_input'][st.session_state['selected_store_for_report']],
                'topics': st.session_state['topics_input'],
                'impact_day': st.session_state['impact_day_input'],
                'quantitative_data': st.session_state['quantitative_data_input']
            }
            
            is_updated = db_manager.save_weekly_data(
                store_id,
                monday_date_str,
                data_to_save,
                st.session_state['generated_report_output'],
                st.session_state['modified_report_output'] # まだ修正がないのでNoneの可能性
            )
            if is_updated:
                st.success("週次レポートが更新されました！")
            else:
                st.success("週次レポートが保存されました！")
            st.session_state['report_id_to_edit'] = db_manager.get_weekly_report(store_id, monday_date_str).get('id') # 保存したレポートのIDを取得

    st.markdown("---")

    # レポート修正エリア (生成済みレポートがある場合のみ表示)
    if st.session_state['generated_report_output'] or st.session_state['modified_report_output']:
        st.header("5. レポートの修正と学習 (任意)")
        st.info("AIが生成したレポートを修正し、「修正して学習」ボタンを押すと、システムがその修正から学び、将来のレポート精度向上に役立てます。")

        report_to_display = st.session_state['modified_report_output'] if st.session_state['modified_report_output'] else st.session_state['generated_report_output']

        modified_trend = st.text_area(
            "**修正後の週全体の動向と要因:**",
            value=report_to_display.get('trend', ''),
            key="modified_trend_input",
            height=200
        )
        modified_factors_str = st.text_input(
            "**修正後の主な要因 (カンマ区切り):**",
            value=", ".join(report_to_display.get('factors', [])),
            key="modified_factors_input"
        )
        modified_questions_str = st.text_area(
            "**修正後のAIへの質問:**",
            value="\n".join(report_to_display.get('questions', [])),
            key="modified_questions_input",
            height=100
        )
        edit_reason = st.text_area(
            "**修正理由 (学習のために重要です):** 何を、なぜ修正したのかを具体的に記述してください。",
            key="edit_reason_input",
            height=100
        )
        
        modified_factors = [f.strip() for f in modified_factors_str.split(',') if f.strip()]
        modified_questions = [q.strip() for q in modified_questions_str.split('\n') if q.strip()]

        if st.button("修正して学習", type="primary", key="learn_from_correction_button"):
            if not edit_reason.strip():
                st.error("修正理由を入力してください。これはAIの学習に不可欠です。")
            else:
                modified_report_data = {
                    "trend": modified_trend,
                    "factors": modified_factors,
                    "questions": modified_questions,
                    "edit_reason": edit_reason
                }
                st.session_state['modified_report_output'] = modified_report_data

                store_id = db_manager.get_store_id_by_name(st.session_state['selected_store_for_report'])
                monday_date_str = st.session_state['selected_monday']
                
                input_data_for_learning = {
                    'daily_reports': {st.session_state['selected_store_for_report']: st.session_state['daily_reports_input'][st.session_state['selected_store_for_report']]},
                    'topics': st.session_state['topics_input'],
                    'impact_day': st.session_state['impact_day_input'],
                    'quantitative_data': st.session_state['quantitative_data_input']
                }

                # DBに保存し、学習エンジンに渡す
                db_manager.save_weekly_data(
                    store_id,
                    monday_date_str,
                    input_data_for_learning, # daily_reports_inputを直接渡す
                    st.session_state['generated_report_output'],
                    modified_report_data
                )
                
                learning_engine.learn_from_correction(
                    input_data=input_data_for_learning,
                    original_output=st.session_state['generated_report_output'],
                    modified_output=modified_report_data
                )
                st.success("修正内容が保存され、システムが学習しました！")
                st.experimental_rerun()


def show_report_history_page():
    st.title("📚 レポート履歴")
    st.markdown("---")

    st.info("ここでは、これまでに作成・保存された週次レポートの一覧を確認できます。")

    all_stores = db_manager.get_all_stores()
    store_names = [s[1] for s in all_stores]
    store_id_map = {s[1]: s[0] for s in all_stores}

    selected_store_name = st.selectbox("表示する店舗を選択:", ["全店舗"] + store_names)

    if selected_store_name == "全店舗":
        reports = db_manager.get_all_weekly_reports()
    else:
        selected_store_id = store_id_map[selected_store_name]
        reports = db_manager.get_all_weekly_reports(selected_store_id)

    if not reports:
        st.write("表示するレポートがありません。")
        return

    report_data = []
    for r in reports:
        # store_name は既に DBManager で追加されているはず
        report_data.append({
            "ID": r['id'],
            "店舗名": db_manager.get_store_name_by_id(r['store_id']), # Store IDから名前を再取得
            "週次レポート (月曜日)": r['monday_date'],
            "最終更新日時": datetime.fromisoformat(r['timestamp']).strftime('%Y/%m/%d %H:%M'),
            "AI生成済み": "はい" if r['has_generated'] else "いいえ",
            "修正済み": "はい" if r['has_modified'] else "いいえ",
            "ダウンロード": f"Download_{r['id']}" # ダミーの列名
        })
    
    df = pd.DataFrame(report_data)

    st.dataframe(df.set_index('ID'), use_container_width=True)

    # レポート詳細表示・ダウンロード
    st.subheader("レポートの詳細表示とダウンロード")
    report_ids = [r['id'] for r in reports]
    
    if report_ids:
        selected_report_id = st.selectbox("詳細を表示・ダウンロードするレポートのIDを選択してください:", report_ids)

        if selected_report_id:
            selected_report_db = next((r for r in reports if r['id'] == selected_report_id), None)
            
            if selected_report_db:
                # DBから最新の完全なレポートデータを再取得
                full_report = db_manager.get_weekly_report(selected_report_db['store_id'], selected_report_db['monday_date'])
                
                if full_report:
                    st.markdown(f"### レポートID: {full_report['id']} - {db_manager.get_store_name_by_id(full_report['store_id'])}店 - 週次: {full_report['monday_date']}")
                    st.write(f"最終更新日時: {datetime.fromisoformat(full_report['timestamp']).strftime('%Y/%m/%d %H:%M')}")

                    # ダウンロード用のデータ整形
                    export_data = {
                        "レポート対象週の月曜日": full_report['monday_date'],
                        "店舗名": db_manager.get_store_name_by_id(full_report['store_id']),
                        "AI生成レポート_動向": full_report['generated_report'].get('trend', '') if full_report.get('generated_report') else '',
                        "AI生成レポート_要因": ", ".join(full_report['generated_report'].get('factors', [])) if full_report.get('generated_report') else '',
                        "AI生成レポート_質問": "\n".join(full_report['generated_report'].get('questions', [])) if full_report.get('generated_report') else '',
                        "修正後レポート_動向": full_report['modified_report'].get('trend', '') if full_report.get('modified_report') else '',
                        "修正後レポート_要因": ", ".join(full_report['modified_report'].get('factors', [])) if full_report.get('modified_report') else '',
                        "修正後レポート_質問": "\n".join(full_report['modified_report'].get('questions', [])) if full_report.get('modified_report') else '',
                        "修正理由": full_report['modified_report'].get('edit_reason', '') if full_report.get('modified_report') else '',
                        "TOPICS": full_report.get('topics', ''),
                        "インパクト大": full_report.get('impact_day', ''),
                        "定量データ": full_report.get('quantitative_data', '')
                    }
                    
                    # 日次レポートの詳細を追加
                    daily_reports = full_report.get('daily_reports', {})
                    for store_name, dates_data in daily_reports.items():
                        for date_str, report_data in dates_data.items():
                            export_data[f"日次動向_{store_name}_{date_str}"] = report_data.get('trend', '')
                            export_data[f"日次要因_{store_name}_{date_str}"] = ", ".join(report_data.get('factors', []))

                    df_export = pd.DataFrame([export_data])
                    
                    st.download_button(
                        label="レポートをExcelでダウンロード",
                        data=get_excel_download_link(df_export, f"週次レポート_{full_report['monday_date']}_{db_manager.get_store_name_by_id(full_report['store_id'])}.xlsx", "ダウンロード"),
                        file_name=f"週次レポート_{full_report['monday_date']}_{db_manager.get_store_name_by_id(full_report['store_id'])}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )

                    st.markdown("#### レポート内容プレビュー")
                    if full_report.get('modified_report'):
                        st.subheader("--- 最終修正版レポート ---")
                        st.markdown("**週全体の動向と要因:**")
                        st.write(full_report['modified_report'].get('trend', ''))
                        st.markdown("**主な要因:**")
                        for i, factor in enumerate(full_report['modified_report'].get('factors', [])):
                            st.write(f"- {factor}")
                        if full_report['modified_report'].get('questions'):
                            st.markdown("**AIへの質問:**")
                            for q in full_report['modified_report'].get('questions', []):
                                st.write(f"- {q}")
                        if full_report['modified_report'].get('edit_reason'):
                            st.markdown("**修正理由:**")
                            st.write(full_report['modified_report'].get('edit_reason', ''))
                    
                    if full_report.get('generated_report'):
                        st.subheader("--- AI生成レポート (オリジナル) ---")
                        st.markdown("**週全体の動向と要因:**")
                        st.write(full_report['generated_report'].get('trend', ''))
                        st.markdown("**主な要因:**")
                        for i, factor in enumerate(full_report['generated_report'].get('factors', [])):
                            st.write(f"- {factor}")
                        if full_report['generated_report'].get('questions'):
                            st.markdown("**AIからの質問:**")
                            for q in full_report['generated_report'].get('questions', []):
                                st.write(f"- {q}")
                    
                    st.subheader("--- 入力データ ---")
                    st.markdown("**日次レポート:**")
                    daily_reports = full_report.get('daily_reports', {})
                    for store_name, dates_data in daily_reports.items():
                        st.markdown(f"**{store_name}店**")
                        for date_str, report_data in dates_data.items():
                            st.markdown(f"  - {date_str} 動向: {report_data.get('trend', 'N/A')}")
                            st.markdown(f"    要因: {', '.join(report_data.get('factors', [])) if report_data.get('factors') else 'N/A'}")

                    st.markdown("**TOPICS:**")
                    st.write(full_report.get('topics', 'N/A'))
                    st.markdown("**インパクト大:**")
                    st.write(full_report.get('impact_day', 'N/A'))
                    st.markdown("**定量データ:**")
                    st.write(full_report.get('quantitative_data', 'N/A'))
            else:
                st.warning("選択されたレポートの詳細を読み込めませんでした。")
    else:
        st.info("レポート履歴がありません。")

def show_settings_page():
    st.title("⚙️ 設定")
    st.markdown("---")

    st.subheader("OpenAI APIキー設定")
    st.info("週次レポート生成にはOpenAI APIキーが必要です。")
    
    # 環境変数から現在のAPIキーを取得
    current_api_key = os.getenv("OPENAI_API_KEY", "")
    
    new_api_key = st.text_input(
        "OpenAI APIキーを入力してください:",
        type="password",
        value=current_api_key,
        help="お持ちのOpenAI APIキーを入力してください。入力されたキーは環境変数として保存されます。変更しない場合は空のままにしてください。"
    )

    if st.button("APIキーを保存"):
        if new_api_key:
            # .envファイルにAPIキーを書き込む
            with open(".env", "w") as f:
                f.write(f"OPENAI_API_KEY={new_api_key}\n")
            # 環境変数にセット（このセッションで即座に反映させるため）
            os.environ["OPENAI_API_KEY"] = new_api_key
            st.success("APIキーが保存されました。")
            # OpenAIクライアントを再初期化
            report_generator.initialize_openai(new_api_key)
        else:
            st.warning("APIキーが入力されていません。")

    st.markdown("---")

    st.subheader("学習データ管理 (開発中)")
    st.info("AIの精度向上に使用される学習データを管理します。")

    learning_stats = db_manager.get_learning_stats()
    st.write(f"登録されているレポート数: **{learning_stats['total_reports']}**")
    st.write(f"ユーザー修正済みレポート数: **{learning_stats['corrections']}**")
    st.write(f"学習パターン数: **{learning_stats['patterns']}**")

    # 学習データのエクスポート機能 (例)
    st.markdown("---")
    st.subheader("学習データのエクスポート")
    if st.button("全学習データをダウンロード (開発者向け)"):
        # 仮の学習データ取得ロジック（実際にはlearning_patternsテーブルから取得）
        conn = db_manager._get_connection()
        learning_data_df = pd.read_sql_query("SELECT * FROM learning_patterns", conn)
        conn.close()

        if not learning_data_df.empty:
            st.download_button(
                label="学習データをCSVでダウンロード",
                data=learning_data_df.to_csv(index=False, encoding='utf-8-sig'),
                file_name="learning_data_export.csv",
                mime="text/csv"
            )
            st.success("学習データをダウンロードしました。")
        else:
            st.warning("ダウンロードする学習データがありません。")


# メインナビゲーション
st.sidebar.title("ナビゲーション")
selection = st.sidebar.radio("Go to", ["週次レポート作成", "レポート履歴", "設定"])

if selection == "週次レポート作成":
    show_report_creation_page()
elif selection == "レポート履歴":
    show_report_history_page()
elif selection == "設定":
    show_settings_page()