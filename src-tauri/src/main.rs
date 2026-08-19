use disk_scope::scan_engine::{ScanEngine, ScanOptions, FileType, ScanResult};
use tauri::{
    plugin::{Builder, TauriPlugin},
    Runtime, Manager, State,
};
use std::sync::{Arc, Mutex};
use std::path::PathBuf;
use serde::{Deserialize, Serialize};

#[derive(Debug, Serialize, Deserialize)]
struct ScanRequest {
    path: String,
    min_size: Option<u64>,
    max_depth: Option<usize>,
    file_types: Option<Vec<String>>,
    follow_symlinks: bool,
}

#[derive(Debug, Serialize, Deserialize)]
struct ScanProgress {
    current_path: String,
    files_scanned: u64,
    dirs_scanned: u64,
    bytes_scanned: u64,
}

#[derive(Debug, Serialize, Deserialize)]
struct ScanResponse {
    total_size: u64,
    total_files: u64,
    total_dirs: u64,
    scan_duration_ms: u64,
    entries: Vec<FileEntry>,
}

#[derive(Debug, Serialize, Deserialize)]
struct FileEntry {
    path: String,
    size: u64,
    modified: String,
    is_dir: bool,
    file_type: String,
}

struct ScanState {
    engine: std::sync::Mutex<Option<disk_scope::scan_engine::ScanEngine>>,
    progress: std::sync::Mutex<Option<disk_scope::scan_engine::ScanProgress>>,
}

impl Default for ScanState {
    fn default() -> Self {
        Self {
            engine: std::sync::Mutex::new(None),
            progress: std::sync::Mutex::new(None),
        }
    }
}

#[tauri::command]
async fn scan_directory(
    state: State<'_, ScanState>,
    request: ScanRequest,
) -> Result<ScanResponse, String> {
    let options = ScanOptions {
        root_path: std::path::PathBuf::from(request.path),
        min_size: request.min_size,
        max_depth: request.max_depth,
        file_types: request.file_types.as_ref().map(|types| {
            types.iter().filter_map(|s| match s.as_str() {
                "file" => Some(disk_scope::scan_engine::FileType::File),
                "directory" => Some(disk_scope::scan_engine::FileType::Directory),
                "audio" => Some(disk_scope::scan_engine::FileType::Audio),
                "video" => Some(disk_scope::scan_engine::FileType::Video),
                "image" => Some(disk_scope::scan_engine::FileType::Image),
                "document" => Some(disk_scope::scan_engine::FileType::Document),
                "archive" => Some(disk_scope::scan_engine::FileType::Archive),
                "code" => Some(disk_scope::scan_engine::FileType::Code),
                "cache" => Some(disk_scope::scan_engine::FileType::Cache),
                "log" => Some(disk_scope::scan_engine::FileType::Log),
                "temporary" => Some(disk_scope::scan_engine::FileType::Temporary),
                "executable" => Some(disk_scope::scan_engine::FileType::Executable),
                _ => None,
            }).collect()
        }),
        follow_symlinks: request.follow_symlinks,
        ..Default::default()
    };

    let engine = disk_scope::scan_engine::ScanEngine::new(options, None)
        .map_err(|e| format!("Failed to create scan engine: {}", e))?;

    let start = std::time::Instant::now();
    let result = engine.scan(&std::path::PathBuf::from(request.path))
        .map_err(|e| format!("Scan failed: {}", e))?;

    let mut entries = Vec::new();
    for entry in result.entries {
        entries.push(FileEntry {
            path: entry.path.to_string_lossy().to_string(),
            size: entry.size,
            modified: entry.modified.duration_since(std::time::UNIX_EPOCH)
                .map(|d| d.as_secs().to_string())
                .unwrap_or_default(),
            is_dir: entry.is_dir,
            file_type: format!("{:?}", entry.file_type),
        });
    }

    Ok(ScanResponse {
        total_size: result.total_size,
        total_files: result.total_files,
        total_dirs: result.total_dirs,
        scan_duration_ms: start.elapsed().as_millis() as u64,
        entries,
    })
}

#[tauri::command]
async fn get_scan_progress() -> Option<disk_scope::scan_engine::ScanProgress> {
    // Return current scan progress
    None
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_fs::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_opener::init())
        .manage(std::sync::Mutex::new(None))
        .invoke_handler(tauri::generate_handler![scan_directory])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}

fn main() {
    run()
}