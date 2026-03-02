// ======================================================
// Granny2 (.gr2) – Educational Pattern Template
// Section-based container structure
// ======================================================

#pragma endian little

// ------------------------------------------------------
// Basic Types
// ------------------------------------------------------

typedef u8      uint8;
typedef u16     uint16;
typedef u32     uint32;
typedef u64     uint64;
typedef float   float32;

// ------------------------------------------------------
// Granny2 Header (Generic Layout)
// ------------------------------------------------------

typedef struct
{
    char        Magic[16];        // Usually contains "Granny" signature
    uint32      HeaderSize;       // Size of this header
    uint32      Version;          // Granny version (varies by build)

    uint32      Platform;         // Target platform
    uint32      FileSize;         // Total file size

    uint32      SectionCount;     // Number of sections
    uint32      SectionTableOffset;

    uint32      RootObjectOffset; // Offset to root object
    uint32      TypeSectionOffset;

    uint64      Reserved0;
    uint64      Reserved1;

} GrannyHeader
<bgcolor=cLtBlue>;


// ------------------------------------------------------
// Section Table Entry
// ------------------------------------------------------

typedef struct
{
    uint32  Offset;           // File offset to section data
    uint32  CompressedSize;   // Size in file
    uint32  DecompressedSize; // Expected size after decompression
    uint32  CompressionType;  // 0 = none, 1 = Oodle0, 2 = Oodle1, etc.

    uint32  RelocationCount;  // Number of relocation entries
    uint32  RelocationOffset; // Offset to relocation table (relative)

    uint32  Flags;
    uint32  Reserved;

} GrannySectionEntry
<bgcolor=cLtGreen>;


// ------------------------------------------------------
// Relocation Entry (Pointer Fixup)
// ------------------------------------------------------

typedef struct
{
    uint32  OffsetInSection;  // Offset where pointer exists
    uint32  TargetSection;    // Target section index
    uint32  TargetOffset;     // Offset inside target section
    uint32  Reserved;

} GrannyRelocation
<bgcolor=cLtYellow>;


// ------------------------------------------------------
// Type Definition Entry (Logical Layer)
// ------------------------------------------------------

typedef struct
{
    uint32  TypeNameOffset;   // Offset to type name string
    uint32  MemberCount;      // Number of members
    uint32  MemberArrayOffset;
    uint32  Size;             // Size of structure

} GrannyTypeDefinition
<bgcolor=cLtOrange>;


// ------------------------------------------------------
// Type Member
// ------------------------------------------------------

typedef struct
{
    uint32  MemberNameOffset;
    uint32  DataType;         // Enum-like value
    uint32  Offset;           // Offset in struct
    uint32  ArraySize;

} GrannyTypeMember
<bgcolor=cLtRed>;


// ------------------------------------------------------
// Root Layout
// ------------------------------------------------------

GrannyHeader header @ 0x00;

GrannySectionEntry sections[header.SectionCount] 
    @ header.SectionTableOffset;


// ------------------------------------------------------
// Section Visualization (Raw Data Blocks)
// ------------------------------------------------------

for (uint32 i = 0; i < header.SectionCount; i++)
{
    struct SectionData
    {
        uint8 data[sections[i].CompressedSize];
    } section_raw 
    @ sections[i].Offset;
}