#include <std/mem.pat>
#include <std/core.pat>

// Granny 3D 파일 매직 넘버 (버전에 따라 다를 수 있음)
// 일반적인 64비트/32비트 Granny 헤더 식별자 확인 필요
using Magic = u8[16];

struct Section {
    u32 format;          // 데이터 포맷 (압축 여부 등)
    u32 data_offset;     // 파일 내 실제 데이터 시작 위치
    u32 data_size;       // 데이터 크기
    u32 expanded_size;   // 압축 해제 시 크기
    u32 alignment;       // 정렬 단위
    u32 field_14;        // 예약된 필드 또는 내부 플래그
    u32 field_18;
    u32 checksum;        // 섹션 무결성 검사값
};

struct GrannyHeader {
    u32 magic_0;         // 0xB8E193CA (표준 리틀 엔디안 기준)
    u32 magic_1;
    u32 version;         // SDK 버전
    u32 file_size;       // 전체 파일 크기
    u32 crc;             // CRC 체크섬
    u32 section_offset;  // 섹션 헤더 배열 시작 위치
    u32 section_count;   // 섹션 개수
    
    // 루트 오브젝트 타입 정보 오프셋
    u32 root_type_offset;
    u32 root_object_offset;
    
    // 태그 및 추가 메타데이터
    u32 tag;
    u32 extra[4];
};

// 실제 데이터 섹션을 시각화하기 위한 구조
struct SectionData {
    u8 data[parent.sections[std::core::array_index()].data_size] [[color("44FF44")]];
};

struct GrannyFile {
    GrannyHeader header [[color("FF5555")]];
    
    // 섹션 헤더 배열로 이동
    $ = header.section_offset;
    Section sections[header.section_count] [[color("5555FF")]];
    
    // 각 섹션의 실제 데이터 위치 표시 (선택 사항)
    /*
    for (u32 i = 0; i < header.section_count; i = i + 1) {
        if (sections[i].data_size > 0) {
            $ = sections[i].data_offset;
            u8 raw_data[sections[i].data_size] [[inline_color("22BB22")]];
        }
    }
    */
};

// 파일 시작 부분에 배치
GrannyFile file @ 0x00;