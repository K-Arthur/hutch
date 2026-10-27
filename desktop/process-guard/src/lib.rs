//! Host process ownership primitives. Platform support is explicit, not inferred
//! from building this crate on another operating system.

pub const CONTRACT_VERSION: u32 = 1;

#[cfg(unix)]
pub mod unix;

#[cfg(windows)]
pub mod windows;
