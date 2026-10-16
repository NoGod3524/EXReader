// SPDX-License-Identifier: GPL-3.0-only
#[tauri::command]
pub async fn convert_book(input: Vec<u8>, from: String, to: String, title: String, author: String, cover: Option<String>) -> Result<Vec<u8>, String> {
    tauri::async_runtime::spawn_blocking(move || exreader_calibre::convert(input, from, to, title, author, cover)).await.map_err(|e| e.to_string())?
}
