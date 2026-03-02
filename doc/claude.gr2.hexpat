/**
 * Granny2 (.gr2) File Format Pattern
 * Based on Norbyte/lslib (https://github.com/Norbyte/lslib/tree/master/LSLib/Granny)
 *
 * Supports: LE32 V1, V2, V6 (Little Endian 32-bit)
 * Tested with: Divinity: Original Sin 2, Baldur's Gate 3
 */

#pragma endian little
#pragma pattern_limit 1000000

import std.io;
import std.mem;

// ─────────────────────────────────────────────
//  Magic Number 정의 (버전별)
// ─────────────────────────────────────────────

// Known magic bytes for detection (LE32 V6 — BG3/DOS2)
// 0xB8 0x67 0xB0 0xCA 0xF8 0x6D 0xB1 0x0F 0x84 0x72 0x8C 0x7E 0x5E 0x19 0x00 0x1E

// ─────────────────────────────────────────────
//  Enums
// ─────────────────────────────────────────────

enum CompressionType : u32 {
    None    = 0,    // 압축 없음
    Oodle0  = 1,    // Oodle 압축 (구버전)
    Oodle1  = 2,    // Oodle 압축 (신버전)
};

enum MemberType : u32 {
    None              = 0,
    Inline            = 1,   // 인라인 구조체 (포인터 없이 직접 포함)
    Reference         = 2,   // 단일 오브젝트 포인터
    ReferenceToArray  = 3,   // 배열 포인터 (count + ptr)
    ArrayOfReferences = 4,   // 포인터 배열
    Variant           = 5,   // 다형성 타입 (TypeDef + Data 쌍)
    UnsignedByte      = 6,   // u8
    Byte              = 7,   // s8
    UnsignedShort     = 8,   // u16
    BinormalInt8      = 9,   // [-1,1] 범위 s8
    NormalUInt8       = 10,  // [0,1] 범위 u8
    Int16             = 11,  // s16
    BinormalInt16     = 12,  // [-1,1] 범위 s16
    NormalUInt16      = 13,  // [0,1] 범위 u16
    Real16            = 14,  // half-float (16bit)
    Int32             = 15,  // s32
    UnsignedInt32     = 16,  // u32
    Real32            = 17,  // float
    Real64            = 18,  // double
    String            = 19,  // null-terminated 문자열 포인터
    Transform         = 20,  // TRS 트랜스폼 (이동/회전/스케일)
    Real32x2          = 21,  // float[2]
    Real32x3          = 22,  // float[3]  (3D 벡터)
    Real32x4          = 23,  // float[4]  (쿼터니언 등)
    Int8x4            = 24,  // s8[4]
    UnsignedInt8x4    = 25,  // u8[4]
    Real32x3x3        = 26,  // float[3][3] 행렬
    Real32x4x4        = 27,  // float[4][4] 행렬
    Empty             = 28,  // 크기 0 더미 타입
    Int32x2           = 29,  // s32[2]
};

// ─────────────────────────────────────────────
//  기본 수학 타입
// ─────────────────────────────────────────────

struct Vec2 {
    float x;
    float y;
} [[color("AADDFF")]];

struct Vec3 {
    float x;
    float y;
    float z;
} [[color("AADDFF")]];

struct Vec4 {
    float x;
    float y;
    float z;
    float w;
} [[color("AADDFF")]];

struct Quat {
    float x;
    float y;
    float z;
    float w;
} [[color("FFDDAA")]];

struct Mat3x3 {
    float m[9];
} [[color("DDFFAA")]];

struct Mat4x4 {
    float m[16];
} [[color("DDFFAA")]];

// GR2 TRS Transform 구조체
struct GR2Transform {
    u32   flags;        // 어떤 성분이 유효한지 비트플래그
    Vec3  translation;
    Quat  rotation;
    Vec3  scale_shear_x;
    Vec3  scale_shear_y;
    Vec3  scale_shear_z;
} [[color("FFAA44")]];

// ─────────────────────────────────────────────
//  섹션 포인터 타입
//  GR2 내부 포인터는 (섹션인덱스 << 24 | 섹션내오프셋) 인코딩
// ─────────────────────────────────────────────

struct SectionPtr {
    u32 offset;     // raw 값: 상위 바이트 = 섹션 인덱스, 하위 3바이트 = 오프셋
} [[
    color("FF8844"),
    format("fmt_section_ptr")
]];

fn fmt_section_ptr(SectionPtr p) {
    u32 sec = (p.offset >> 24) & 0xFF;
    u32 off = p.offset & 0x00FFFFFF;
    return std::format("Sec[{}] @ 0x{:06X}", sec, off);
};

// ─────────────────────────────────────────────
//  섹션 헤더
// ─────────────────────────────────────────────

struct SectionHeader {
    CompressionType compression           [[color("FF4444")]];   // 압축 방식
    u32             data_offset           [[color("44FF44")]];   // 파일 내 데이터 절대 오프셋
    u32             data_size             [[color("44FF44")]];   // 압축된 데이터 크기 (bytes)
    u32             decompressed_size     [[color("88FF88")]];   // 압축 해제 후 크기 (bytes)
    u32             alignment             [[color("AAAAAA")]];   // 메모리 정렬 단위 (보통 4 or 8)
    u16             first16bit_section    [[color("BBBBBB")]];   // 16bit 포인터 재배치 시작 섹션
    u16             first8bit_section     [[color("BBBBBB")]];   // 8bit 포인터 재배치 시작 섹션
    u32             relocation_offset     [[color("FFCC44")]];   // 재배치 테이블 오프셋 (섹션 내 상대)
    u32             relocation_count      [[color("FFCC44")]];   // 재배치 항목 수
    u32             mixed_marshalling_offset [[color("FF88FF")]]; // 혼합 마샬링 테이블 오프셋
    u32             mixed_marshalling_count  [[color("FF88FF")]]; // 혼합 마샬링 항목 수
} [[size(44)]];

// ─────────────────────────────────────────────
//  파일 헤더
// ─────────────────────────────────────────────

struct GR2Header {
    // ── Magic (16 bytes) ──
    u8  magic[16]                       [[color("FF2222"), comment("파일 식별자 — 버전/엔디안 결정")]];

    // ── 헤더 메타 ──
    u32 header_size                     [[color("FFAA22"), comment("헤더 전체 크기 (bytes)")]];
    u32 header_format                   [[color("FFAA22"), comment("헤더 포맷 버전")]];
    u8  reserved[8]                     [[color("555555"), comment("예약됨 (0x00)")]];

    // ── 파일 정보 ──
    u32 version                         [[color("44DDFF"), comment("Granny 버전 (보통 7)")]];
    u32 file_size                       [[color("44DDFF"), comment("전체 파일 크기 (bytes)")]];
    u32 crc32                           [[color("FF8888"), comment("파일 데이터 CRC32 체크섬")]];

    // ── 섹션 테이블 ──
    u32 section_offset                  [[color("AAFFAA"), comment("SectionHeader 배열 시작 오프셋")]];
    u32 section_count                   [[color("AAFFAA"), comment("섹션 수 (보통 6)")]];

    // ── Root 오브젝트 참조 ──
    // 각각 상위 1바이트=섹션인덱스, 하위 3바이트=섹션 내 오프셋
    u32 root_type_definition            [[color("FF88FF"), comment("Root TypeDefinition 위치")]];
    u32 root_object                     [[color("FF88FF"), comment("Root 오브젝트(GR2ArtRoot) 위치")]];

    // ── 기타 ──
    u32 user_tag                        [[color("888888"), comment("사용자 정의 태그값")]];
    u8  extra_tags[16]                  [[color("666666"), comment("게임별 확장 정보")]];
};

// ─────────────────────────────────────────────
//  재배치 (Relocation) 항목
//  포인터 픽스업 — 섹션 내부의 포인터 값을
//  실제 메모리 주소로 변환하는 정보
// ─────────────────────────────────────────────

struct RelocationEntry {
    u32 offset_in_section   [[color("FFCC44"), comment("이 오프셋의 포인터 값을 재배치")]];
    u32 target_section      [[color("FF8844"), comment("대상 섹션 인덱스")]];
    u32 target_offset       [[color("FF8844"), comment("대상 섹션 내 오프셋")]];
};

// ─────────────────────────────────────────────
//  Mixed Marshalling 항목
//  엔디안 변환이 필요한 데이터 블록 기술
// ─────────────────────────────────────────────

struct MixedMarshallingEntry {
    u32 count               [[color("FF88FF"), comment("항목 수")]];
    u32 offset_in_section   [[color("FF88FF"), comment("섹션 내 오프셋")]];
    u32 ref_type_section    [[color("CC66FF"), comment("TypeDef 섹션 인덱스")]];
    u32 ref_type_offset     [[color("CC66FF"), comment("TypeDef 섹션 내 오프셋")]];
};

// ─────────────────────────────────────────────
//  타입 정의 (TypeDefinition / MemberDefinition)
//  GR2의 자기기술적(self-describing) 핵심
//  각 구조체 멤버가 이 구조로 기술됨
// ─────────────────────────────────────────────

struct MemberDefinition {
    MemberType  type                    [[color("88FFDD"), comment("데이터 타입")]];
    u32         name_ptr                [[color("FFDDAA"), comment("멤버 이름 문자열 포인터")]];
    u32         children_ptr            [[color("AADDFF"), comment("하위 TypeDef 포인터 (Inline/Reference용)")]];
    u32         array_size_or_extra0    [[color("DDAAFF"), comment("배열 크기 or 부가정보[0]")]];
    u32         extra1                  [[color("DDAAFF"), comment("부가정보[1]")]];
    u32         extra2                  [[color("DDAAFF"), comment("부가정보[2]")]];
    u32         unknown                 [[color("666666")]];
};

// ─────────────────────────────────────────────
//  섹션 데이터 원시 뷰
//  (각 섹션의 실제 데이터를 바이트 배열로 표시)
// ─────────────────────────────────────────────

struct SectionData<auto offset, auto size> {
    u8 data[size] @ offset;
};

// ─────────────────────────────────────────────
//  전체 GR2 파일 구조 진입점
// ─────────────────────────────────────────────

struct GR2File {
    // 1. 파일 헤더
    GR2Header header                    [[comment("GR2 파일 헤더")]];

    // 2. 섹션 헤더 배열
    //    헤더의 section_offset 위치에서 section_count 개 읽기
    SectionHeader sections[header.section_count] @ header.section_offset
                                        [[comment("섹션 헤더 배열 (보통 6개)")]];
};

// ─────────────────────────────────────────────
//  파일에 패턴 적용
// ─────────────────────────────────────────────

GR2File gr2 @ 0x00;


// ─────────────────────────────────────────────
//  섹션별 raw 데이터 뷰 (섹션 수에 맞게 배치)
//  섹션 헤더 파싱 후 각 섹션의 바이트를 확인 가능
// ─────────────────────────────────────────────

// Section 0: Main/Root 데이터
u8 section0_data[gr2.sections[0].data_size]
    @ gr2.sections[0].data_offset
    [[name("Section0_Main"), color("334455"),
      comment("Root 오브젝트 및 메인 구조체 데이터")]];

// Section 1: 타입 정의 (TypeDefinition 트리)
u8 section1_data[gr2.sections[1].data_size]
    @ gr2.sections[1].data_offset
    [[name("Section1_TypeDefs"), color("334433"),
      comment("MemberDefinition 트리 — 자기기술적 타입 정보")]];

// Section 2: 포인터 재배치 데이터
u8 section2_data[gr2.sections[2].data_size]
    @ gr2.sections[2].data_offset
    [[name("Section2_Relocations"), color("554433"),
      comment("포인터 픽스업 테이블")]];

// Section 3: Vertex Buffer
u8 section3_data[gr2.sections[3].data_size]
    @ gr2.sections[3].data_offset
    [[name("Section3_VertexBuffer"), color("335544"),
      comment("버텍스 위치/법선/UV 등 원시 데이터")]];

// Section 4: Index/Triangle Buffer
u8 section4_data[gr2.sections[4].data_size]
    @ gr2.sections[4].data_offset
    [[name("Section4_TriangleBuffer"), color("553344"),
      comment("폴리곤 인덱스 데이터")]];

// Section 5: 문자열 테이블 (String Pool)
u8 section5_data[gr2.sections[5].data_size]
    @ gr2.sections[5].data_offset
    [[name("Section5_StringPool"), color("445533"),
      comment("null-terminated 문자열 풀")]];


// ─────────────────────────────────────────────
//  재배치 테이블 뷰
//  각 섹션의 relocation 테이블을 직접 파싱
// ─────────────────────────────────────────────

// Section 0 재배치 항목들
RelocationEntry sec0_relocs[gr2.sections[0].relocation_count]
    @ gr2.sections[0].data_offset + gr2.sections[0].relocation_offset
    [[name("Section0_Relocations"), color("FFCC44"),
      comment("Section0 포인터 픽스업 항목")]];

// Section 1 재배치 항목들
RelocationEntry sec1_relocs[gr2.sections[1].relocation_count]
    @ gr2.sections[1].data_offset + gr2.sections[1].relocation_offset
    [[name("Section1_Relocations"), color("FFCC44"),
      comment("Section1 포인터 픽스업 항목")]];

// Section 3 (Vertex) 재배치 항목들 (있을 경우)
RelocationEntry sec3_relocs[gr2.sections[3].relocation_count]
    @ gr2.sections[3].data_offset + gr2.sections[3].relocation_offset
    [[name("Section3_Relocations"), color("FFCC44"),
      comment("Section3 포인터 픽스업 항목")]];


// ─────────────────────────────────────────────
//  Mixed Marshalling 뷰
// ─────────────────────────────────────────────

MixedMarshallingEntry sec0_marshalling[gr2.sections[0].mixed_marshalling_count]
    @ gr2.sections[0].data_offset + gr2.sections[0].mixed_marshalling_offset
    [[name("Section0_MixedMarshalling"), color("FF88FF"),
      comment("엔디안 변환 기술 항목 (Section0)")]];

MixedMarshallingEntry sec1_marshalling[gr2.sections[1].mixed_marshalling_count]
    @ gr2.sections[1].data_offset + gr2.sections[1].mixed_marshalling_offset
    [[name("Section1_MixedMarshalling"), color("FF88FF"),
      comment("엔디안 변환 기술 항목 (Section1)")]];
