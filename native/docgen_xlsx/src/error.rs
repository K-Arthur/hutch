//! Error type shared by the JSON boundary and the writer.
//!
//! Every failure is a data problem (bad spec, Excel bound, render failure). The Python
//! binding maps `WriteError` to `ValueError`; nothing here panics on user input.

use std::fmt;

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum WriteError {
    /// The caller's JSON is not a valid, in-bounds workbook specification.
    InvalidSpec(String),
    /// rust_xlsxwriter rejected the workbook while rendering (e.g. an Excel output limit).
    Render(String),
}

impl WriteError {
    pub fn invalid(detail: impl Into<String>) -> Self {
        WriteError::InvalidSpec(detail.into())
    }

    pub fn render(detail: impl Into<String>) -> Self {
        WriteError::Render(detail.into())
    }
}

impl fmt::Display for WriteError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            WriteError::InvalidSpec(detail) => write!(f, "bad xlsx specification: {detail}"),
            WriteError::Render(detail) => write!(f, "xlsx render failed: {detail}"),
        }
    }
}

impl std::error::Error for WriteError {}
