//! PyO3 binding: `write_workbook(spec_json: str) -> bytes`.

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::PyBytes;

use crate::error::WriteError;

/// Render the normalized workbook spec (JSON) and return the `.xlsx` bytes.
///
/// Raises `ValueError` for an invalid or out-of-bounds specification. The GIL is
/// released while parsing and writing; the input string is copied once at the boundary.
#[pyfunction]
fn write_workbook(py: Python<'_>, spec_json: &str) -> PyResult<Py<PyBytes>> {
    let owned = spec_json.to_owned();
    let data = py
        .detach(move || -> Result<Vec<u8>, WriteError> {
            let spec = crate::parse(&owned)?;
            crate::write_workbook(&spec)
        })
        .map_err(|error| PyValueError::new_err(error.to_string()))?;
    Ok(PyBytes::new(py, &data).unbind())
}

#[pymodule]
fn hutch_docgen_native(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(write_workbook, module)?)?;
    module.add("__version__", env!("CARGO_PKG_VERSION"))?;
    Ok(())
}
