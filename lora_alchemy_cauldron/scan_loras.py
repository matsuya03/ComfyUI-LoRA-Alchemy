import os
import sys
import logging
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import traceback
import argparse # Moved from inside __main__ block to top

# Add the parent directory (ComfyUI-LoRA-Alchemy/) to sys.path
custom_nodes_dir = os.path.dirname(os.path.abspath(__file__))  # lora_alchemy_cauldron/
parent_dir = os.path.dirname(custom_nodes_dir)  # ComfyUI-LoRA-Alchemy/
sys.path.insert(0, parent_dir)
comfy_dir = os.path.dirname(os.path.dirname(parent_dir))

from lora_alchemy_cauldron.worker import process_new_lora

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("AlchemyScanner")

# Optional YAML support
try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False
    logger.warning("yaml package not installed. Skipping extra_model_paths.yaml parsing.")

def parse_extra_model_paths():
    """Parse extra_model_paths.yaml to find custom lora directories"""
    if not HAS_YAML:
        return []
    
    extra_paths_file = os.path.join(comfy_dir, "extra_model_paths.yaml")
    custom_lora_dirs = []
    
    if not os.path.exists(extra_paths_file):
        logger.debug(f"extra_model_paths.yaml not found at {extra_paths_file}")
        return []
    
    try:
        with open(extra_paths_file, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        if not config:
            logger.warning("extra_model_paths.yaml is empty")
            return []
            
        for config_name, paths_config in config.items():
            base_path = paths_config.get("base_path", "")
            
            # Expand ~ if used
            if base_path.startswith("~"):
                base_path = os.path.expanduser(base_path)
            
            # If path is relative, make it absolute to comfy_dir
            if not os.path.isabs(base_path):
                base_path = os.path.join(comfy_dir, base_path)
                
            loras_paths = paths_config.get("loras", "")
            if loras_paths:
                # YAML can have a single string or a list or newline separated string
                if isinstance(loras_paths, str):
                    for p in loras_paths.split("\n"):
                        p = p.strip()
                        if p:
                            full_path = os.path.join(base_path, p)
                            custom_lora_dirs.append(full_path)
                            logger.debug(f"Added LoRA path from {config_name}: {full_path}")
                elif isinstance(loras_paths, list):
                    for p in loras_paths:
                        full_path = os.path.join(base_path, str(p))
                        custom_lora_dirs.append(full_path)
                        logger.debug(f"Added LoRA path from {config_name}: {full_path}")
                            
    except Exception as e:
        logger.error(f"Error parsing extra_model_paths.yaml: {e}")
        logger.debug(traceback.format_exc())
        
    return custom_lora_dirs

def find_lora_directories():
    """Find potential LoRA directories including those in extra_model_paths.yaml"""
    dirs_to_check = []
    
    # Standard ComfyUI models/loras
    std_lora_dir = os.path.join(comfy_dir, "models", "loras")
    if os.path.exists(std_lora_dir):
        dirs_to_check.append(std_lora_dir)
        logger.debug(f"Found standard LoRA dir: {std_lora_dir}")
        
    # Standard ComfyUI models/lyCORIS
    std_lycoris_dir = os.path.join(comfy_dir, "models", "lyCORIS")
    if os.path.exists(std_lycoris_dir):
        dirs_to_check.append(std_lycoris_dir)
        logger.debug(f"Found standard LyCORIS dir: {std_lycoris_dir}")
        
    # Append paths from extra_model_paths.yaml
    extra_dirs = parse_extra_model_paths()
    for d in extra_dirs:
        if os.path.exists(d):
            dirs_to_check.append(d)
        else:
            logger.warning(f"Configured LoRA path does not exist: {d}")
        
    return list(set(dirs_to_check))  # remove duplicates

def process_lora_safe(file_path: Path) -> bool:
    """Safe wrapper for process_new_lora"""
    try:
        result_id = process_new_lora(file_path)
        return bool(result_id)
    except Exception as e:
        logger.error(f"Failed to process {file_path.name}: {e}")
        logger.debug(traceback.format_exc())
        return False

def scan_all_loras(max_workers: int = 4, rebuild: bool = False) -> bool:
    """Scan and register all LoRAs"""
    from lora_alchemy_cauldron.db_manager import DB_FILE_PATH
    
    if rebuild:
        logger.info("Rebuild flag detected. Clearing existing lora_db.json...")
        try:
            if os.path.exists(DB_FILE_PATH):
                os.remove(DB_FILE_PATH)
                logger.info("Successfully deleted existing database.")
        except Exception as e:
            logger.error(f"Failed to delete database: {e}")
            return False

    logger.info("Starting bulk scan of existing LoRAs...")
    
    search_dirs = find_lora_directories()
    if not search_dirs:
        logger.error("Could not locate any LoRA directories.")
        logger.info("Checked paths:")
        logger.info(f"  - {os.path.join(comfy_dir, 'models', 'loras')}")
        logger.info(f"  - {os.path.join(comfy_dir, 'models', 'lyCORIS')}")
        return False
    
    target_files = []
    for d in search_dirs:
        logger.info(f"Scanning directory: {d}")
        # Find all .safetensors recursively
        for path in Path(d).rglob("*.safetensors"):
            target_files.append(path)
    
    if not target_files:
        logger.warning("No .safetensors files found in the located directories.")
        return False
    
    logger.info(f"Found {len(target_files)} LoRAs. Starting processing...")
    
    # Process with thread pool
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        results = []
        for idx, (file_path, result) in enumerate(
            zip(target_files, executor.map(process_lora_safe, target_files)), 1
        ):
            results.append(result)
            status = "✅" if result else "❌"
            logger.info(f"[{idx}/{len(target_files)}] {status} {file_path.name}")
    
    success_count = sum(results)
    fail_count = len(results) - success_count
    
    logger.info(f"\n{'='*60}")
    logger.info(f"Scan complete!")
    logger.info(f"  ✅ Successfully registered: {success_count}")
    logger.info(f"  ❌ Failed: {fail_count}")
    logger.info(f"  📊 Total: {len(results)}")
    logger.info(f"{'='*60}\n")
    
    return fail_count == 0

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scan and register LoRA files.")
    parser.add_argument("--rebuild", action="store_true", help="Delete the existing database and rebuild from scratch")
    args = parser.parse_args()
    
    success = scan_all_loras(max_workers=4, rebuild=args.rebuild)
    sys.exit(0 if success else 1)
