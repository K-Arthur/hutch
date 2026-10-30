use super::*;

fn cell(array: &str) -> Result<Cell, serde_json::Error> {
    let wrapped = format!("{{\"cell\":[{array}]}}");
    #[derive(Deserialize)]
    struct Holder {
        cell: Cell,
    }
    serde_json::from_str::<Holder>(&wrapped).map(|holder| holder.cell)
}

#[test]
fn decodes_str_num_date_formula() {
    assert_eq!(cell("\"str\",\"007\"").unwrap(), Cell::Str("007".into()));
    assert_eq!(cell("\"num\",1.5").unwrap(), Cell::Num(1.5));
    assert_eq!(cell("\"date\",\"2026-01-15\"").unwrap(), Cell::Date(46_037));
    assert_eq!(
        cell("\"formula\",\"=SUM(A1:A2)\",3").unwrap(),
        Cell::Formula {
            expr: "SUM(A1:A2)".into(),
            cached: 3.0
        }
    );
}

#[test]
fn rejects_malformed_cells() {
    assert!(cell("\"num\"").is_err());
    assert!(cell("\"str\",1").is_err());
    assert!(cell("\"bogus\",1").is_err());
    assert!(cell("\"num\",1,2").is_err());
    assert!(cell("\"date\",\"2026-02-30\"").is_err());
    assert!(cell("\"date\",\"2026-1-5\"").is_err());
}

#[test]
fn parses_spec_and_validates_bounds() {
    let json = r#"{"sheets":[{"name":"S","header":["h"],"rows":[[["num",1]]],
                            "freeze":true,"col_widths":[12.5]}]}"#;
    let spec = parse(json).unwrap();
    assert_eq!(spec.sheets[0].name, "S");
    assert_eq!(spec.sheets[0].col_widths, vec![12.5]);

    let too_wide = r#"{"sheets":[{"name":"S","col_widths":[300]}]}"#;
    assert!(parse(too_wide).is_err());
    let bad_name = r#"{"sheets":[{"name":"a/b"}]}"#;
    assert!(parse(bad_name).is_err());
    let duplicate = r#"{"sheets":[{"name":"S"},{"name":"s"}]}"#;
    assert!(parse(duplicate).is_err());
    let unknown_key = r#"{"sheets":[{"name":"S","bogus":1}]}"#;
    assert!(parse(unknown_key).is_err());
    let no_sheets = r#"{"sheets":[]}"#;
    assert!(parse(no_sheets).is_err());
}

#[test]
fn freeze_requires_header() {
    let json = r#"{"sheets":[{"name":"S","rows":[[["num",1]]],"freeze":true}]}"#;
    assert!(parse(json).is_err());
}

#[test]
fn dates_round_trip_known_serials() {
    assert_eq!(parse_iso_date("1899-12-30").unwrap(), 0);
    assert_eq!(parse_iso_date("1900-01-01").unwrap(), 2);
    assert_eq!(parse_iso_date("1970-01-01").unwrap(), 25_569);
    assert_eq!(parse_iso_date("2026-01-15").unwrap(), 46_037);
    assert_eq!(parse_iso_date("2024-02-29").unwrap(), 45_351);
    assert!(parse_iso_date("2023-02-29").is_err());
    assert!(parse_iso_date("0000-01-01").is_err());
}
