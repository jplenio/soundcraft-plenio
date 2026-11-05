//! A score's MIDI file from the studio is read without trust: random bytes never panic.

use proptest::prelude::*;

proptest! {
    #![proptest_config(ProptestConfig { cases: 500, ..ProptestConfig::default() })]

    #[test]
    fn splicing_random_files_is_an_error_not_a_panic(bytes in prop::collection::vec(any::<u8>(), 0..512), index in 0usize..6) {
        let mut file = b"MThd\0\0\0\x06\0\x01\0\x02\x03\xc0".to_vec();
        file.extend(bytes);
        let _ = soundcraft_plenio_commands::splice_midi(&file, &[(index, "Vocal".into(), soundcraft_midi::Sequence::default())]);
    }
}
