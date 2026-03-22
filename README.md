# LoRA Alchemy Cauldron (LoRA錬金釜) - 総合ドキュメント

LoRA Alchemy Cauldronは、画像生成AI向けに追加学習モデル(LoRA)を統合管理し、最適なWeight（適用強度）の自動計算や、LoRA間の相性（競合）を判定するシステムです。ComfyUIのプロセス内で完全に動作し、別サーバーを立てる必要はありません。

---

## 🚀 1. クイックスタート (環境構築)

### 1.1 前提条件
- Python 3.10以上
- [Ollama](https://ollama.com/) (ローカルLLMを用いたタグ推論を利用する場合)
- 依存ライブラリのインストール
  ```bash
  pip install -r requirements.txt
  ```
  ※ Stability Matrix 環境では、別途 `pip install pyyaml filelock` が必要な場合があります。

### 1.2 環境変数の設定
プロジェクト直下にある `.env.example` をコピーして `.env` を作成します。

```bash
cp .env.example .env
```

`.env` を開き、必要に応じて以下の値を設定してください。
- `HF_TOKEN`: HuggingFaceからタグ等のメタデータを取得する場合のAPIトークン
- `OLLAMA_BASE_URL`: Ollamaの起動先URL（デフォルトは `http://localhost:11434`）
- `LLM_MODEL_NAME`: Role分類に使用するOllamaのモデル名（デフォルトは `mistral:instruct`）

### 1.3 初回セットアップ時の重要事項
- **データベースの生成:** `lora_db.json` は Git 管理対象外です。初回起動時やデータの整合性が取れなくなった場合は、`python lora_alchemy_cauldron/scan_loras.py` を実行して、ローカルの LoRA ファイルからデータベースを再生成してください。
- **SSL証明書の生成:** 通信の暗号化に使用する `.pem` ファイルは Git 管理対象外です。各環境で `mkcert` 等を使用して再生成してください。

---

## 🛠 2. システム構成と操作方法

当システムはComfyUIに統合されており、**「LoRAの自動スキャン監視」**と**「相性最適化エンジン」**を内部で実行します。

### 2.1 バックグラウンド監視スレッド (Watcher & Worker)

**役割:** ComfyUI起動時に自動的にバックグラウンドで開始され、`models/loras` ディレクトリを監視します。新規の `.safetensors` ファイルが追加されると、自動的にスキャンし、タグ抽出とロール分類（Ollamaを利用）を行い、データベース(`lora_db.json`)に登録します。大量のLoRAがある場合は初回起動時に `scan_loras.py` を手動実行して一括登録することも可能です。

```bash
# 手動での一括スキャン（推奨）
python lora_alchemy_cauldron/scan_loras.py
```

### 2.2 [ComfyUI Extension] LoRA Alchemy Node

**役割:** ComfyUIのノードグラフ上でユーザーがLoRAを選択し、重みやPin設定を調整するための専用カスタムノードです。内部の最適化エンジンを呼び出し、選択された複数のLoRA間の「相性スコア（競合など）」を算出し、ユーザーが固定（Pin）したWeightを優先しながら最適なWeightを自動再計算してノードUIに反映します。

**インストールと設定:**
1. リポジトリを ComfyUI の `custom_nodes` ディレクトリ内にクローン（または配置）します。
   例: `custom_nodes/ComfyUI-LoRA-Alchemy`
2. ComfyUI を起動後、ノードメニューから `LoRA Alchemy Node` を追加します。
3. ノード内のテキストパネル（Alchemy Log）に最適化結果が自動で表示されます。

---

## 🧠 3. 高度な機能 (Advanced Features)

### 3.1 Influence Classifier & Influence Map
LoRAが画像生成に及ぼす影響領域をカテゴリ（Face, Body, Clothing, Pose, Lighting, Style, Background）ごとにスコア化し、可視化します。

**領域衝突ロジック:**
単なるタグ比較ではなく、「どの領域を奪い合っているか」を判定します。例えば「Face同士が干渉している（-50点）」といった具体的な領域単位の相性を算出します。

**Influence Map の可視化:**
ノード上のテキストログに、現在のブレンドが画像に与える影響のパラメーターマップがグラフ表示されます。
```text
🗺️ Influence Map:
Face         █████████░ 90
Style        ████████░░ 80
...
```

### 3.2 LoRA Encyclopedia (LoRA図鑑)
ノードを右クリックし **「📖 Show LoRA Encyclopedia」** を選択することで、現在選択されているLoRAの詳細情報（ファイル名、ベースモデル、ロール、トリガーワード、解説、プレビュー画像）をポップアップで一括表示します。

---

## 📦 4. 外部統合と最適化

### 4.1 Stability Matrix 統合
Stability Matrixが生成するローカルメタデータ（JSON、プレビュー画像）を優先的に活用することで、ネットワーク負荷を99%削減し、スキャン速度を大幅に向上させています。
- **Priority 1:** Stability Matrix のローカルデータ
- **Priority 2:** HuggingFace / Civitai 等の外部API
- **Priority 3:** `.safetensors` ヘッダー内包データ

### 4.2 ハッシュ計算とファイル安定化
- **ハッシュの統一:** スキャン時と使用時で同一のハッシュ計算（LoRA ID）を保証します。
- **書き込み完了待機:** 大容量LoRA（500MB超）のコピー中でも、ファイルサイズが安定するまで待機してから処理を開始するため、破損データの登録を防ぎます。

---

## ⚙️ 5. 本番環境・運用ガイド

### 5.1 推奨設定 (.env)
- **高性能サーバー:** `HASH_METHOD=full`, `OLLAMA_TIMEOUT=60`
- **低リソース環境:** `HASH_METHOD=fast`, `OLLAMA_TIMEOUT=30`

### 5.2 API リトライとエラーハンドリング
- **Exponential Backoff:** ネットワーク一時障害時に自動リトライを行います。
- **安全なUI操作:** ノード削除時のUIクリーンアップなど、ComfyUIのDOM構造を破壊しない設計になっています。

### 5.3 複数PC・NAS環境での運用
- **共有フォルダの活用:** ComfyUI の `extra_model_paths.yaml` を使用して、LoRA のパスを NAS などの共有フォルダに向けることで、複数の PC から同じ LoRA 資産を共有して利用可能です。
- **環境ごとのデータベース構築:** `lora_db.json` は Git 管理対象外であり、各環境のローカルに保持されます。新しい PC 環境をセットアップした際は、その環境で `python lora_alchemy_cauldron/scan_loras.py` を実行し、共有フォルダ内の LoRA をスキャンしてローカルのデータベースを構築してください。

---

## 🧪 6. テストと動作確認

DBへのCRUD操作、相性判定、Weight最適化アルゴリズムが機能するかをテストします。

```bash
# ユニットテスト (pytest導入済みの場合)
python -m pytest lora_alchemy_cauldron/test_core.py
```

---

## 📂 7. 構成ファイル

- `__init__.py`: ComfyUI ノード初期化・バックグラウンドサービス起動
- `nodes.py`: LoRA Alchemy ノード本体・API実装
- `lora_alchemy_cauldron/`: 最適化エンジン及びバックグラウンド処理のコアライブラリ
- `js/`: UIコンポーネント (Alchemy Log, LoRA Encyclopedia)
- `lora_db.json`: システム統合データベース (自動生成)
