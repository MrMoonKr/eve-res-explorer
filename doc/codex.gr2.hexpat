#pragma endian little
#pragma pattern_limit 2000000

/*
 * Granny2 (.gr2) pattern for ImHex
 * Based on:
 *   https://github.com/Norbyte/lslib/tree/master/LSLib/Granny
 *   - LSLib/Granny/GR2/Format.cs
 *   - LSLib/Granny/GR2/Reader.cs
 *   - LSLib/Granny/GR2/Writer.cs
 *
 * Notes:
 * - This pattern targets little-endian GR2 files (the common DOS2/BG3 case).
 * - Section offsets for section headers are interpreted as:
 *     absolute_offset = 0x20 (magic size) + header.sections_offset
 *   matching LSLib's read/write behavior.
 */

enum CompressionType : u32 {
    None = 0,
    Oodle0 = 1,
    Oodle1 = 2,
    Oodle4 = 4
};

enum SectionType : u32 {
    Main = 0,
    TrackGroup = 1,
    Skeleton = 2,
    Mesh = 3,
    StructDefinitions = 4,
    FirstVertexData = 5
};

enum MemberType : s32 {
    None = 0,
    Inline = 1,
    Reference = 2,
    ReferenceToArray = 3,
    ArrayOfReferences = 4,
    VariantReference = 5,
    ReferenceToVariantArray = 7,
    String = 8,
    Transform = 9,
    Real32 = 10,
    Int8 = 11,
    UInt8 = 12,
    BinormalInt8 = 13,
    NormalUInt8 = 14,
    Int16 = 15,
    UInt16 = 16,
    BinormalInt16 = 17,
    NormalUInt16 = 18,
    Int32 = 19,
    UInt32 = 20,
    Real16 = 21,
    EmptyReference = 22
};

struct Magic {
    u8 signature[16];
    u32 headers_size;
    u32 header_format;
    u32 reserved1;
    u32 reserved2;
};

struct SectionReference {
    u32 section;
    u32 offset;
};

struct HeaderCommon {
    u32 version;
    u32 file_size;
    u32 crc32;
    u32 sections_offset;
    u32 num_sections;
    SectionReference root_type;
    SectionReference root_node;
    u32 tag;
    u32 extra_tags[4];
};

struct HeaderV7Tail {
    u32 string_table_crc;
    u32 reserved1;
    u32 reserved2;
    u32 reserved3;
};

struct SectionHeader {
    CompressionType compression;
    u32 offset_in_file;
    u32 compressed_size;
    u32 uncompressed_size;
    u32 alignment;
    u32 first16bit;
    u32 first8bit;
    u32 relocations_offset;
    u32 num_relocations;
    u32 mixed_marshalling_data_offset;
    u32 num_mixed_marshalling_data;
};

struct RelocationEntry {
    u32 offset_in_section;
    SectionReference target;
};

struct MixedMarshallingEntry {
    u32 count;
    u32 offset_in_section;
    SectionReference type_definition;
};

struct RawBlock<auto size> {
    u8 data[size];
};

struct CompressedRelocationBlock {
    u32 compressed_size;
    u8 data[compressed_size];
};

//Magic magic @ 0x00;
//HeaderCommon header @ 0x20;

/*if (header.version >= 7) {
    HeaderV7Tail header_v7_tail @ (0x20 + 0x38);
}

SectionHeader sections[header.num_sections] @ (0x20 + header.sections_offset);
*/
/*
for (u32 i = 0; i < header.num_sections; i++) {
    if (sections[i].compressed_size > 0) {
        RawBlock<sections[i].compressed_size> section_data @ sections[i].offset_in_file;
    }

    if (sections[i].num_relocations > 0) {
        if (sections[i].compression == CompressionType::Oodle4) {
            CompressedRelocationBlock relocations_compressed @ sections[i].relocations_offset;
        } else {
            RelocationEntry relocations[sections[i].num_relocations] @ sections[i].relocations_offset;
        }
    }

    if (sections[i].num_mixed_marshalling_data > 0) {
        if (sections[i].compression == CompressionType::Oodle4) {
            CompressedRelocationBlock mixed_marshalling_compressed @ sections[i].mixed_marshalling_data_offset;
        } else {
            MixedMarshallingEntry mixed_marshalling[sections[i].num_mixed_marshalling_data]
                @ sections[i].mixed_marshalling_data_offset;
        }
    }
}
*/

struct GR2Header {
    u8          m_Magic[16] ;
    u32         m_HeaderSize ;
    u32         m_HeaderFormat ;
    u32         m_Reserved1 ;
    u32         m_Reserved2 ;

};

struct GR2File {
    GR2Header   m_Header ;
};


GR2File g_File @ 0x00 ;