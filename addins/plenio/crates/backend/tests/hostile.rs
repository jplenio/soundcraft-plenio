//! Everything the studio sends is read without trust: random input never panics.

use proptest::prelude::*;
use soundcraft_plenio_backend::song::{Job, Record, ScoreInfo, parse_srt};

fn json_value() -> impl Strategy<Value = serde_json::Value> {
    let leaf = prop_oneof![
        Just(serde_json::Value::Null),
        any::<bool>().prop_map(serde_json::Value::Bool),
        any::<i64>().prop_map(|n| serde_json::json!(n)),
        any::<f64>().prop_map(|f| serde_json::json!(f)),
        ".{0,40}".prop_map(serde_json::Value::String),
    ];
    leaf.prop_recursive(4, 64, 8, |inner| {
        prop_oneof![
            prop::collection::vec(inner.clone(), 0..8).prop_map(serde_json::Value::Array),
            prop::collection::btree_map(
                prop_oneof![
                    Just("id".to_string()),
                    Just("status".to_string()),
                    Just("result".to_string()),
                    Just("files".to_string()),
                    Just("documents".to_string()),
                    Just("seeds".to_string()),
                    Just("progress".to_string()),
                    ".{0,8}".prop_map(String::from)
                ],
                inner,
                0..8
            )
            .prop_map(|m| serde_json::Value::Object(m.into_iter().collect())),
        ]
    })
}

proptest! {
    #![proptest_config(ProptestConfig { cases: 400, ..ProptestConfig::default() })]

    #[test]
    fn jobs_and_records_read_anything(v in json_value()) {
        let _ = Job::parse(&v);
        let r = Record::parse(&v);
        prop_assert!(r.seconds.is_finite() && r.seconds >= 0.0);
        prop_assert!(r.stars.is_none_or(|s| (0.0..=5.0).contains(&s)));
    }

    #[test]
    fn scores_read_anything(text in "(X:1\n|Q:[0-9/= ]{0,12}\n|M:[0-9C|/]{0,5}\n|K:[A-Gb#m]{0,4}\n|% [a-z ]{0,10}\n|V: [A-Za-z]{0,6}( clef=treble)?\n|[a-gz0-9|\"A-G]{0,30}\n){0,40}") {
        if let Some(s) = ScoreInfo::parse(&text) {
            prop_assert!(s.bpm.is_finite() && s.bpm > 0.0);
            prop_assert!(s.bar_seconds().is_finite());
        }
    }

    #[test]
    fn subtitles_read_anything(text in "([0-9]{0,3}\n|[0-9:,]{0,14} --> [0-9:,.]{0,14}\n|.{0,20}\n|\n){0,30}") {
        for cue in parse_srt(&text) {
            prop_assert!(cue.start.is_finite() && cue.end >= cue.start);
        }
    }
}
