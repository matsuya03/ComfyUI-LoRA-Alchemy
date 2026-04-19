import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { ComfyWidgets } from "../../scripts/widgets.js";

function debounce(func, wait) {
    let timeout;
    return function (...args) {
        clearTimeout(timeout);
        timeout = setTimeout(() => func.apply(this, args), wait);
    };
}

app.registerExtension({
    name: "LoRA.AlchemyNode",
    async nodeCreated(node) {
        if (node.comfyClass !== "LoRAAlchemyNode") return;

        // Auto Balance Button
        const autoBalanceBtn = node.addWidget("button", "🎯 Auto Balance", "balance", () => {
            if (!isUpdatingFromApi) executeAutoBalance();
        });

        const showEncyclopedia = async (customLoras) => {
            let loras = customLoras;
            if (!loras) {
                loras = [];
                for (let i = 1; i <= 5; i++) {
                    const nameW = node.widgets.find(w => w.name === `lora_${i}_name`);
                    if (nameW && nameW.value !== "None") {
                        loras.push(nameW.value);
                    }
                }
            }
            if (!loras || loras.length === 0) {
                logWidget.value = "❌ Please select a valid LoRA first to view details.";
                app.graph.setDirtyCanvas(true);
                return;
            }

            const escapeHtml = (text) => {
                const div = document.createElement('div');
                div.textContent = text;
                return div.innerHTML;
            };

            // Create a modal dialog
            const overlay = document.createElement("div");
            Object.assign(overlay.style, {
                position: "fixed", top: "0", left: "0", width: "100vw", height: "100vh",
                backgroundColor: "rgba(0, 0, 0, 0.7)", zIndex: "10000",
                display: "flex", justifyContent: "center", alignItems: "center",
                padding: "20px"
            });

            // =========================================================
            // ★ ここを追加：背景（暗転部分）をクリックしたら閉じる
            // =========================================================
            overlay.addEventListener("click", (e) => {
                if (e.target === overlay) {
                    document.body.removeChild(overlay);
                }
            });
            // =========================================================

            const modal = document.createElement("div");
            Object.assign(modal.style, {
                position: "relative",
                backgroundColor: "#222", color: "#fff", padding: "20px",
                borderRadius: "10px", width: "80%", maxWidth: "800px", maxHeight: "80vh",
                overflowY: "auto", boxShadow: "0 4px 15px rgba(0,0,0,0.5)", fontFamily: "sans-serif"
            });

            const closeBtn = document.createElement("div");
            closeBtn.innerText = "✖";
            Object.assign(closeBtn.style, {
                position: "absolute", right: "20px", top: "20px", cursor: "pointer", fontSize: "24px"
            });
            closeBtn.onclick = () => document.body.removeChild(overlay);

            modal.appendChild(closeBtn);
            const title = document.createElement("h2");
            title.innerText = "📖 LoRA Encyclopedia";
            title.style.marginTop = "0";
            modal.appendChild(title);

            overlay.appendChild(modal);
            document.body.appendChild(overlay);

            for (const loraName of loras) {
                const itemDiv = document.createElement("div");
                Object.assign(itemDiv.style, {
                    borderTop: "1px solid #444", padding: "20px 0", display: "flex", gap: "20px"
                });

                itemDiv.innerHTML = `<div><span style="color: #888;">Loading details for <b>${loraName}</b>...</span></div>`;
                modal.appendChild(itemDiv);

                try {
                    const response = await api.fetchApi("/alchemy/lora_details", {
                        method: "POST", headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ lora_name: loraName })
                    });

                    if (response.ok) {
                        let data = await response.json();

                        // =========================================================
                        // ★ 新機能：オンロード時の自動画像フェッチ（オートフェッチ）
                        // ローカルDBに画像URLがなく、CivitaiのIDがわかっている場合は自動で取得に行く
                        // =========================================================
                        const toCivitaiRed = url => url ? url.replace(/https?:\/\/(image\.)?civitai\.com\//g, (_, sub) => `https://${sub || ''}civitai.red/`) : url;

                        if ((!data.reference_image_urls || data.reference_image_urls.length === 0) && data.civitai_version_id) {
                            try {
                                const civRes = await fetch(`https://civitai.red/api/v1/model-versions/${data.civitai_version_id}`);
                                if (civRes.ok) {
                                    const civData = await civRes.json();
                                    if (civData.images && civData.images.length > 0) {
                                        data.reference_image_urls = [];
                                        civData.images.forEach(img => {
                                            if (img.url) data.reference_image_urls.push(img.url);
                                        });
                                    }
                                }
                            } catch (e) {
                                console.warn(`Failed to auto-fetch images for ${loraName}:`, e);
                            }
                        }
                        // =========================================================

                        // 左側：テキスト情報エリア
                        let html = `<div style="flex: 1; min-width: 0; padding-right: 15px;">`;
                        html += `<h3 style="margin: 0 0 10px 0; color: #4CAF50; word-break: break-all;">${escapeHtml(data.name)}</h3>`;
                        html += `<div style="font-size: 0.9em; margin-bottom: 5px;"><b>Base Model:</b> ${data.base_model}</div>`;
                        if (data.roles && data.roles.length > 0) {
                            html += `<div style="font-size: 0.9em; margin-bottom: 5px;"><b>Roles:</b> ${data.roles.map(r => r.type).join(', ')}</div>`;
                        }
                        if (data.trigger_words && data.trigger_words.length > 0) {
                            html += `<div style="font-size: 0.9em; margin-bottom: 10px; color: #ffaa00; word-break: break-all;"><b>Triggers:</b> ${data.trigger_words.join(', ')}</div>`;
                        }
                        if (data.description) {
                            html += `<div style="font-size: 0.85em; background: #111; padding: 10px; border-radius: 5px; max-height: 200px; overflow-y: auto; white-space: pre-wrap; line-height: 1.4; scrollbar-width: thin; scrollbar-color: #555 #111;">${data.description}</div>`;
                        } else {
                            html += `<div style="font-size: 0.85em; color: #888; font-style: italic;">No description available.</div>`;
                        }
                        html += `</div>`;

                        // 右側：ギャラリーエリア（固定幅）
                        let galleryHtml = `<div style="width: 320px; flex-shrink: 0; display: flex; flex-direction: column; gap: 10px;">`;

                        // 1. メイン画像
                        const mainImgUrl = data.preview_image_path
                            ? `/alchemy/view_image?path=${encodeURIComponent(data.preview_image_path)}`
                            : (data.reference_image_urls && data.reference_image_urls.length > 0 ? toCivitaiRed(data.reference_image_urls[0]) : null);

                        if (mainImgUrl) {
                            galleryHtml += `
                                <img src="${mainImgUrl}" style="width: 100%; border-radius: 8px; object-fit: contain; background: #111; max-height: 300px; cursor: pointer;" 
                                alt="Main Preview" onclick="window.open(this.src, '_blank')"
                                onerror="if(!this.dataset.fb){this.dataset.fb='1';this.src=this.src.replace('civitai.red','civitai.com')}else{this.style.display='none';}" />
                            `;
                        }

                        // 2. 水平スクロールギャラリー ＋ ステータス表示
                        if (data.reference_image_urls && data.reference_image_urls.length > 0) {
                            galleryHtml += `<div style="display: flex; gap: 8px; overflow-x: auto; padding-bottom: 8px; scrollbar-width: thin; scrollbar-color: #555 #222;">`;
                            data.reference_image_urls.forEach(url => {
                                const redUrl = toCivitaiRed(url);
                                galleryHtml += `
                                    <img src="${redUrl}" style="height: 100px; width: auto; border-radius: 5px; object-fit: cover; cursor: pointer; background: #222; transition: transform 0.2s;"
                                    alt="Reference" onmouseover="this.style.transform='scale(1.05)'" onmouseout="this.style.transform='scale(1)'" onclick="window.open(this.src, '_blank')" onerror="if(!this.dataset.fb){this.dataset.fb='1';this.src=this.src.replace('civitai.red','civitai.com')}else{this.style.display='none';}" />
                                `;
                            });
                            galleryHtml += `</div>`;
                            galleryHtml += `<div style="font-size: 0.8em; color: #888; text-align: right; margin-top: -5px;">${data.reference_image_urls.length} images (Click to enlarge)</div>`;
                        } else {
                            // ★ なぜ画像が出ないのかの理由を表示する
                            let reason = "No additional images available";
                            if (!data.civitai_version_id) {
                                reason = "No Civitai ID found in DB. <br>(Please run scan_loras.py)";
                            } else {
                                reason = "No gallery images found on Civitai API.";
                            }
                            galleryHtml += `<div style="color: #888; font-size: 0.8em; text-align: center; padding: 10px; border: 1px dashed #444; border-radius: 8px;">${reason}</div>`;
                        }

                        galleryHtml += `</div>`;
                        itemDiv.innerHTML = html + galleryHtml;
                    } else {
                        itemDiv.innerHTML = `<div style="color: #ff5555;">Failed to load details for ${loraName}</div>`;
                    }
                } catch (e) {
                    itemDiv.innerHTML = `<div style="color: #ff5555;">Error: ${e.message}</div>`;
                }
            }
        };

        // Removed encBtn

        // "All" Toggle Widget (To be moved to the top later)
        const toggleAllW = node.addWidget("toggle", "All", false, (val) => {
            for (let i = 1; i <= 5; i++) {
                const nameW = node.widgets.find(w => w.name === `lora_${i}_name`);
                const pinW = node.widgets.find(w => w.name === `lora_${i}_pin`);
                if (nameW && nameW.value !== "None" && pinW) {
                    pinW.value = val;
                }
            }
            app.graph.setDirtyCanvas(true);
        });

        // 期待される「lora_1_name」の上に「All」トグルを移動する
        const lora1Idx = node.widgets.findIndex(w => w.name === "lora_1_name");
        if (lora1Idx >= 0) {
            const allIdx = node.widgets.indexOf(toggleAllW);
            node.widgets.splice(allIdx, 1);
            node.widgets.splice(lora1Idx, 0, toggleAllW);
        }

        // ComfyUIネイティブの複数行テキストウィジェットを安全に追加（DOM直接操作の廃止）
        const logWidget = ComfyWidgets["STRING"](node, "alchemy_log", ["STRING", { multiline: true }], app).widget;
        logWidget.inputEl.readOnly = true;
        logWidget.value = "⏳ Ready...";

        // UIがウィジェットを更新するためのフラグ（無限ループ完全防止）
        let isUpdatingFromApi = false;

        const executeAutoBalance = async () => {
            if (isUpdatingFromApi) return;
            try {
                let loras = [];
                for (let i = 1; i <= 5; i++) {
                    const nameW = node.widgets.find(w => w.name === `lora_${i}_name`);
                    const pinW = node.widgets.find(w => w.name === `lora_${i}_pin`);

                    if (nameW && nameW.value !== "None") {
                        loras.push({
                            lora_name: nameW.value,
                            is_pinned: pinW ? pinW.value : false
                        });
                    }
                }

                if (loras.length === 0) {
                    logWidget.value = "ℹ️ No LoRAs selected.";
                    return;
                }

                logWidget.value = "⏳ Balancing weights...";

                const response = await api.fetchApi("/alchemy/autobalance", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ loras: loras })
                });

                if (!response.ok) {
                    logWidget.value = `❌ Auto Balance Backend Error: ${response.status}`;
                    return;
                }

                const data = await response.json();

                isUpdatingFromApi = true;

                if (data.balanced_weights) {
                    for (let i = 1; i <= 5; i++) {
                        const nameW = node.widgets.find(w => w.name === `lora_${i}_name`);
                        const weightW = node.widgets.find(w => w.name === `lora_${i}_weight`);
                        const pinW = node.widgets.find(w => w.name === `lora_${i}_pin`);

                        // 固定(pinned)されていないものだけを更新
                        if (nameW && weightW && pinW && !pinW.value) {
                            const optWeight = data.balanced_weights[nameW.value];
                            if (optWeight !== undefined) {
                                weightW.value = parseFloat(optWeight.toFixed(3));
                            }
                        }
                    }
                }

                logWidget.value = "✅ Auto Balance applied!\n";
                if (data.warnings && data.warnings.length > 0) {
                    logWidget.value += `⚠️ Notes:\n`;
                    data.warnings.forEach(w => {
                        // 1. ':' の後ろで改行
                        let formatted = w.replace(/:\s*/, ":\n      ");
                        // 2. ' and ' の部分を ' 💥 vs ' にして前後に改行を入れる
                        formatted = formatted.replace(/'\s+and\s+'/g, "'\n      💥 vs\n      '");
                        logWidget.value += `  • ${formatted}\n\n`;
                    });
                }

                // ★ 悪さをしていた node.setSize は削除しました！
                app.graph.setDirtyCanvas(true);
            } catch (e) {
                logWidget.value = `❌ Error: ${e.message}`;
            } finally {
                isUpdatingFromApi = false;

                // Auto Balance適用後、全てをPin(固定)して、直後の最適化で上書きされないようにする
                for (let i = 1; i <= 5; i++) {
                    const nameW = node.widgets.find(w => w.name === `lora_${i}_name`);
                    const pinW = node.widgets.find(w => w.name === `lora_${i}_pin`);
                    if (nameW && nameW.value !== "None" && pinW) {
                        pinW.value = true;
                    }
                }
                const allW = node.widgets.find(w => w.name === "All");
                if (allW) allW.value = true;

                // バランス適用後、再度最適化判定を走らせてログを通常状態に戻す
                debouncedUpdate();
            }
        };

        const updateAlchemy = async () => {
            // APIによる自動更新中は、再度APIを叩かないようにブロック
            if (isUpdatingFromApi) return;

            try {
                let loras = [];
                for (let i = 1; i <= 5; i++) {
                    const nameW = node.widgets.find(w => w.name === `lora_${i}_name`);
                    const weightW = node.widgets.find(w => w.name === `lora_${i}_weight`);
                    const pinW = node.widgets.find(w => w.name === `lora_${i}_pin`);

                    if (nameW && nameW.value !== "None") {
                        loras.push({
                            lora_name: nameW.value,
                            preferred_weight: weightW ? weightW.value : 1.0,
                            is_pinned: pinW ? pinW.value : false
                        });
                    }
                }

                if (loras.length === 0) {
                    logWidget.value = "ℹ️ No LoRAs selected.";
                    return;
                }

                logWidget.value = "⏳ Optimizing...";

                const response = await api.fetchApi("/alchemy/optimize", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ loras: loras })
                });

                if (!response.ok) {
                    logWidget.value = `❌ Backend Error: ${response.status}`;
                    return;
                }

                const data = await response.json();

                // ----------------------------------------------------------------
                // ここからUIの値をプログラムで変更するため、ロックをかける
                // ----------------------------------------------------------------
                isUpdatingFromApi = true;

                if (data.optimized_weights) {
                    for (let i = 1; i <= 5; i++) {
                        const nameW = node.widgets.find(w => w.name === `lora_${i}_name`);
                        const weightW = node.widgets.find(w => w.name === `lora_${i}_weight`);
                        const pinW = node.widgets.find(w => w.name === `lora_${i}_pin`);

                        if (nameW && weightW && pinW && !pinW.value) {
                            const optWeight = data.optimized_weights[nameW.value];
                            if (optWeight !== undefined) {
                                // 値を書き換えても isUpdatingFromApi が true なのでループしない
                                weightW.value = parseFloat(optWeight.toFixed(3));
                            }
                        }
                    }
                }

                // Ollamaと判定エンジンの結果（ログテキスト）を構築
                let logText = `🧪 Base Model: ${data.base_model || "Unknown"}\n`;
                logText += `📊 Score: ${data.compatibility_score} / 100\n\n`;

                if (data.influence_map) {
                    logText += `🗺️ Influence Map:\n`;
                    const maxBarLen = 10;
                    for (const [region, val] of Object.entries(data.influence_map)) {
                        const filled = Math.round((val / 100) * maxBarLen);
                        const bar = "█".repeat(filled) + "░".repeat(maxBarLen - filled);
                        logText += `${region.padEnd(12)} ${bar} ${val}\n`;
                    }
                    logText += `\n`;
                }

                if (data.warnings && data.warnings.length > 0) {
                    logText += `⚠️ Warnings:\n`;
                    data.warnings.forEach(w => {
                        let formatted = w.replace(/:\s*/, ":\n      ");
                        formatted = formatted.replace(/'\s+and\s+'/g, "'\n      💥 vs\n      '");
                        logText += `  • ${formatted}\n\n`;
                    });
                } else {
                    logText += `✓ No conflicts detected.\n`;
                }

                logWidget.value = logText;

                // ★ 悪さをしていた node.setSize は削除しました！
                app.graph.setDirtyCanvas(true);

            } catch (e) {
                logWidget.value = `❌ Error: ${e.message}`;
            } finally {
                // 処理が終わったらロックを解除し、ユーザー操作を再び受け付ける
                isUpdatingFromApi = false;
            }
        };

        const debouncedUpdate = debounce(updateAlchemy, 600);

        // 安全なイベントフック (LiteGraph標準のフックを使用)
        const onPropertyChanged = node.onPropertyChanged;
        node.onPropertyChanged = function (property, value) {
            if (onPropertyChanged) onPropertyChanged.apply(this, arguments);
            debouncedUpdate();
        };

        // ウィジェット変更のフック (シンプル版)
        node.widgets.forEach(w => {
            if (w.name && w.name.startsWith("lora_")) {
                const origCb = w.callback;
                w.callback = function (...args) {
                    if (origCb) origCb.apply(this, args);
                    if (!isUpdatingFromApi) debouncedUpdate();
                };
            }
        });

        // =========================================================================
        // 右クリックメニュー (Context Menu) の拡張
        // =========================================================================
        const origGetExtraMenuOptions = node.getExtraMenuOptions;
        node.getExtraMenuOptions = function (canvas, options) {
            // 元のメニューオプションがあれば引き継ぐ
            if (origGetExtraMenuOptions) {
                origGetExtraMenuOptions.apply(this, arguments);
            }

            // 区切り線を追加
            options.push(null);

            // カスタムメニューを追加
            options.push({
                content: "📖 Show LoRA Encyclopedia",
                callback: () => {
                    let activeLoras = [];
                    for (let i = 1; i <= 5; i++) {
                        const nameW = this.widgets.find(w => w.name === `lora_${i}_name`);
                        if (nameW && nameW.value !== "None") {
                            activeLoras.push(nameW.value);
                        }
                    }

                    if (activeLoras.length > 0) {
                        // 既に実装済みのポップアップ関数を呼び出す
                        showEncyclopedia(activeLoras);
                    } else {
                        logWidget.value = "❌ Please select at least one LoRA to view details.";
                        app.graph.setDirtyCanvas(true);
                    }
                }
            });
        };
    }
});
