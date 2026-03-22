import os
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any

import folder_paths
import comfy.sd
from server import PromptServer
from aiohttp import web

import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from lora_alchemy_cauldron.hash_utils import compute_lora_id_safe
from lora_alchemy_cauldron.config import HASH_METHOD, HASH_CHUNK_SIZE_MB

logger = logging.getLogger(__name__)

@PromptServer.instance.routes.post("/alchemy/optimize")
async def alchemy_optimize_endpoint(request):
    try:
        data = await request.json()
        
        id_to_name_map: Dict[str, str] = {}
        active_lora_ids: List[str] = []
        
        if "loras" not in data:
            return web.json_response({"error": "Missing 'loras' field"}, status=400)
            
        for lora_req in data["loras"]:
            lora_name = lora_req.get("lora_name")
            if not lora_name or lora_name == "None":
                continue
                
            try:
                full_path_str = folder_paths.get_full_path("loras", lora_name)
                
                if not full_path_str:
                    logger.warning(f"LoRA file not found in paths: {lora_name}")
                    lora_req["error"] = f"LoRA not found: {lora_name}"
                    continue
                
                lora_id = compute_lora_id_safe(Path(full_path_str), method=HASH_METHOD, fallback_to_stem=True)
                if not lora_id:
                    logger.error(f"Failed to compute LoRA ID: {lora_name}")
                    lora_req["error"] = f"Failed to compute ID: {lora_name}"
                    continue
                    
                lora_req["lora_id"] = lora_id
                id_to_name_map[lora_id] = lora_name
                active_lora_ids.append(lora_id)
            except Exception as e:
                logger.error(f"Error processing {lora_name}: {e}")
                lora_req["error"] = str(e)
                
        if not active_lora_ids:
            return web.json_response({"error": "No valid LoRAs found for optimization"}, status=400)

        from lora_alchemy_cauldron.compatibility import evaluate_compatibility
        from lora_alchemy_cauldron.weight_optimizer import optimize_weights
        from lora_alchemy_cauldron.db_manager import LoRADatabase
        
        db = LoRADatabase()
        active_loras = []
        for lid in active_lora_ids:
            lora = db.get_lora(lid)
            if not lora:
                logger.warning(f"LoRA with id '{lid}' not found in database. Please run scan_loras.py.")
                return web.json_response({"error": f"LoRA '{id_to_name_map.get(lid, lid)}' not found in database. Run the scanner first."}, status=404)
            active_loras.append(lora)
            
        warnings = []
        
        total_compatibility_score = 100
        if len(active_loras) > 1:
            lowest_score = 100
            for i in range(len(active_loras)):
                for j in range(i + 1, len(active_loras)):
                    score, wp_warnings = evaluate_compatibility(active_loras[i], active_loras[j])
                    warnings.extend(wp_warnings)
                    if score < lowest_score:
                        lowest_score = score
            total_compatibility_score = lowest_score

        current_weights = {}
        pinned_loras = []
        for lora_req in data["loras"]:
            if "lora_id" in lora_req:
                l_id = lora_req["lora_id"]
                current_weights[l_id] = float(lora_req.get("preferred_weight", 1.0))
                if lora_req.get("is_pinned", False):
                    pinned_loras.append(l_id)
                    
        detected_base_model = active_loras[0].base_model if active_loras else data.get("base_model", "SDXL")

        optimized_weights, weight_warnings = optimize_weights(
            active_loras=active_loras,
            current_weights=current_weights,
            pinned_loras=set(pinned_loras),
            base_model=detected_base_model
        )
        warnings.extend(weight_warnings)

        all_confidences = []
        for lora in active_loras:
            target_roles = lora.user_override.roles if lora.user_override.roles else lora.roles
            all_confidences.extend([r.confidence for r in target_roles])
        
        avg_confidence = sum(all_confidences) / len(all_confidences) if all_confidences else 1.0
        
        if avg_confidence >= 0.8:
            confidence_level = "High"
        elif avg_confidence >= 0.5:
            confidence_level = "Medium"
        else:
            confidence_level = "Low"

        new_weights = {}
        for lora_id, weight in optimized_weights.items():
            lora_name = id_to_name_map.get(lora_id, lora_id)
            new_weights[lora_name] = weight
            
        from lora_alchemy_cauldron.influence_classifier import calculate_influence_map
        total_influence_map = {
            "Face": 0, "Body": 0, "Clothing": 0, "Lighting": 0, "Background": 0, "Style": 0, "Pose": 0
        }
        for lora in active_loras:
            l_map = calculate_influence_map(lora)
            weight = optimized_weights.get(lora.lora_id, 1.0)
            for k, v in l_map.items():
                total_influence_map[k] = max(total_influence_map[k], min(100, int(v * weight)))

        result_json = {
            "base_model": detected_base_model,
            "optimized_weights": new_weights,
            "compatibility_score": total_compatibility_score,
            "confidence_level": confidence_level,
            "influence_map": total_influence_map,
            "warnings": warnings
        }
            
        return web.json_response(result_json)
        
    except Exception as e:
        logger.error(f"Alchemy Node Error: {e}", exc_info=True)
        return web.json_response({"error": str(e)}, status=500)


@PromptServer.instance.routes.post("/alchemy/autobalance")
async def alchemy_autobalance_endpoint(request):
    try:
        data = await request.json()
        
        id_to_name_map = {}
        active_lora_ids = []
        pinned_loras = set()
        current_weights = {}
        
        if "loras" not in data:
            return web.json_response({"error": "Missing 'loras' field"}, status=400)
            
        for lora_req in data["loras"]:
            lora_name = lora_req.get("lora_name")
            if not lora_name or lora_name == "None":
                continue
                
            try:
                full_path_str = folder_paths.get_full_path("loras", lora_name)
                if not full_path_str:
                    continue
                    
                lora_id = compute_lora_id_safe(Path(full_path_str), method=HASH_METHOD, fallback_to_stem=True)
                if lora_id:
                    id_to_name_map[lora_id] = lora_name
                    active_lora_ids.append(lora_id)
                    
                    if lora_req.get("is_pinned"):
                        pinned_loras.add(lora_id)
                        # 固定されているものは現在のWeightを優先する
                        current_weights[lora_id] = float(lora_req.get("preferred_weight", 1.0))
            except Exception as e:
                logger.error(f"Error processing {lora_name} for auto balance: {e}")
                
        if not active_lora_ids:
            return web.json_response({"error": "No valid LoRAs found for auto balance"}, status=400)

        # =================================================================
        # ★ ここを修正！ 古いauto_balanceではなく最新のoptimize_weightsを呼ぶ
        # =================================================================
        from lora_alchemy_cauldron.weight_optimizer import optimize_weights
        from lora_alchemy_cauldron.db_manager import LoRADatabase
        
        db = LoRADatabase()
        active_loras = []
        for lid in active_lora_ids:
            lora = db.get_lora(lid)
            if lora:
                active_loras.append(lora)
                # 固定されていないものは、DBに記録された推奨Weightを初期値とする
                if lid not in current_weights:
                    current_weights[lid] = lora.compatibility_rules.preferred_weight
                    
        detected_base_model = active_loras[0].base_model if active_loras else data.get("base_model", "SDXL")
        
        balanced_weights, warnings = optimize_weights(
            active_loras=active_loras,
            current_weights=current_weights,
            pinned_loras=pinned_loras,
            base_model=detected_base_model
        )
        # =================================================================
        
        new_weights = {}
        for lora_id, weight in balanced_weights.items():
            lora_name = id_to_name_map.get(lora_id, lora_id)
            new_weights[lora_name] = weight
            
        return web.json_response({
            "balanced_weights": new_weights,
            "warnings": warnings
        })
    except Exception as e:
        logger.error(f"Auto Balance Error: {e}", exc_info=True)
        return web.json_response({"error": str(e)}, status=500)

@PromptServer.instance.routes.post("/alchemy/lora_details")
async def alchemy_lora_details_endpoint(request):
    try:
        data = await request.json()
        lora_name = data.get("lora_name")
        if not lora_name or lora_name == "None":
            return web.json_response({"error": "Invalid lora_name"}, status=400)
            
        full_path_str = folder_paths.get_full_path("loras", lora_name)
        if not full_path_str:
            return web.json_response({"error": f"LoRA not found: {lora_name}"}, status=404)
            
        lora_id = compute_lora_id_safe(Path(full_path_str), method=HASH_METHOD, fallback_to_stem=True)
        if not lora_id:
            return web.json_response({"error": "Failed to compute ID"}, status=500)
            
        from lora_alchemy_cauldron.db_manager import LoRADatabase
        db = LoRADatabase()
        lora = db.get_lora(lora_id)
        
        if not lora:
            return web.json_response({"error": "LoRA not in database. Scan required."}, status=404)
            
        return web.json_response({
            "name": lora.name,
            "roles": [{"type": r.type, "confidence": r.confidence} for r in lora.roles],
            "description": lora.metadata.description,
            "preview_image_path": lora.metadata.preview_image_path,
            "reference_image_urls": getattr(lora.metadata, "reference_image_urls", []),
            "civitai_version_id": getattr(lora.metadata, "civitai_version_id", None),
            "base_model": lora.base_model,
            "trigger_words": lora.metadata.trigger_words,
            "tags": lora.metadata.tags[:30]
        })
    except Exception as e:
        logger.error(f"LoRA Details Error: {e}", exc_info=True)
        return web.json_response({"error": str(e)}, status=500)

@PromptServer.instance.routes.get("/alchemy/view_image")
async def alchemy_view_image_endpoint(request):
    try:
        image_path = request.rel_url.query.get("path")
        if not image_path or not os.path.exists(image_path):
            return web.Response(status=404, text="Image not found")
            
        return web.FileResponse(image_path)
    except Exception as e:
        logger.error(f"View Image Error: {e}", exc_info=True)
        return web.Response(status=500, text=str(e))

class LoRAAlchemyNode:
    def __init__(self):
        self.loaded_lora = None

    @classmethod
    def INPUT_TYPES(s):
        lora_files = ["None"] + folder_paths.get_filename_list("loras")
        
        inputs = {
            "required": {
                "model": ("MODEL",),
                "clip": ("CLIP",),
            },
            "optional": {}
        }
        
        for i in range(1, 6):
            inputs["optional"][f"lora_{i}_name"] = (lora_files,)
            inputs["optional"][f"lora_{i}_weight"] = ("FLOAT", {"default": 1.0, "min": 0.0, "max": 3.0, "step": 0.01})
            inputs["optional"][f"lora_{i}_pin"] = ("BOOLEAN", {"default": False})
            
        return inputs

    RETURN_TYPES = ("MODEL", "CLIP", "STRING")
    RETURN_NAMES = ("MODEL", "CLIP", "ALCHEMY_LOG")
    FUNCTION = "apply_loras"
    CATEGORY = "loaders"

    def apply_loras(self, model, clip, **kwargs):
        alchemy_log = []
        
        for i in range(1, 6):
            lora_name = kwargs.get(f"lora_{i}_name", "None")
            if lora_name == "None":
                continue
                
            weight = kwargs.get(f"lora_{i}_weight", 0.0)
            if weight <= 0.0:
                continue
                
            lora_path = folder_paths.get_full_path("loras", lora_name)
            if not lora_path:
                logger.warning(f"LoRA not found: {lora_name}")
                alchemy_log.append(f"Warning: LoRA not found: {lora_name}")
                continue
                
            try:
                lora_data = comfy.utils.load_torch_file(lora_path, safe_load=True)
                model, clip = comfy.sd.load_lora_for_models(model, clip, lora_data, weight, weight)
                alchemy_log.append(f"Loaded: {lora_name} (Weight: {weight:.3f})")
            except Exception as e:
                logger.error(f"Error loading LoRA {lora_name}: {e}")
                alchemy_log.append(f"Error loading {lora_name}: {e}")
                
        log_output = "\n".join(alchemy_log) if alchemy_log else "No LoRAs applied."
        return (model, clip, log_output)
