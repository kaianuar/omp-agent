//! DiskScope - A fast, cross-platform disk space analyzer
//! 
//! This is the main entry point that demonstrates the workspace structure.
//! The actual application is split into three crates:
//! - scan-engine: Core scanning logic
//! - gui: Tauri + React + egui frontend
//! - cli: Command-line interface

fn main() {
    println!("DiskScope - Disk Space Analyzer");
    println!("================================");
    println!();
    println!("This is a workspace with three crates:");
    println!("  - scan-engine: Core scanning logic (library)");
    println!("  - gui: Tauri + React + egui desktop app (binary)");
    println!("  cli: Command-line interface (binary)");
    println!();
    println!("Run the CLI:");
    println!("  cargo run --bin diskscope -- scan ~/Downloads");
    println!();
    println!("Run the GUI:");
    println!("  cargo tauri dev   (in crates/gui)");
    println!();
    println!("Build release:");
    println!("  cargo tauri build (in crates/gui)");
}