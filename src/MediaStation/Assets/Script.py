from dataclasses import dataclass
from enum import IntEnum
import pprint

from asset_extraction_framework.Asserts import assert_equal

from .. import global_variables
from ..Primitives.Datum import Datum

## Aims to support decompilation from Media Script bytecode.
## Newer titles have very little bytecode in CXT files, but 
## earlier titles have a lot. It seems that the scripting for 
## newer titles is baked into the EXE, not in the CXTs.
##
## Figuring out this bytecode would have been nearly impossible
## if not for the U.S. English version of "If You Give a Mouse a Cookie",
## whose Script assets included debug strings that held human-readable 
## Media Script!

class InstructionType(IntEnum):
    FunctionCall = 0x0067
    Operand = 0x0066
    VariableReference = 0x0065

class Opcodes(IntEnum):
    # Equality tests have this form:
    #  [Opcode.TestEquality, [], []]
    # for example, the code
    #  IF ( var_root_IsInteractive == TRUE )
    # compiles to this:
    #  [Opcode.TestEquality, [Opcode.GetValue, [VariableId], 4],
    #  [OperandType.Literal, 1]]
    # This seems to be the only opcode that accepts non-immediate values.
    TestEquality = 202
    # Variable assignments have this form:
    #  [Opcode.VariableAssignment, VariableId, unknown (seems to be always 4)]
    #  [OperandType.(Literal|AssetId), Operand]
    # For example, this puts the literal integer 0 in variable 118: 
    #  [203, 118, 4]
    #  [153, 0]
    # Parameters seem to be stored in the variable slots starting with "1".
    # For example, function parameter 1 is stored in slot [1]. 
    AssignVariable = 203
    GetValue = 207 # ? Got this from the if statement, not sure if right.
    # Routine calls have this form:
    #  [Opcode.CallRoutine, FunctionId, ParametersCount]
    # Followed by the actual parameters to pass to the function.
    # Functions with low ID numbers are "built-in" functions, and 
    # functions with large ID numbers are user-defined functions.
    UnkRelatedToVariableAssignment = 214 # Appears when we are referencing variables.
    CallRoutine = 219
    # Method calls are like function calls, but they have an implicit "self"
    # parameter that is always the first. For example:
    #  @self . mouseActivate ( TRUE ) ;
    # compiles to:
    #  [220, 210, 0] - [Opcode.CallMethod, BuiltInFunction.MouseActivate, 0 parameters]
    #  [156, 123]    - [OperandType.AssetId, 123 (asset ID for self - this is pre-computed)]
    #  [151, 1]      - [OperandType.Literal, 1 (literal for TRUE)]
    CallMethod = 220
    UnkSomethingWithFunctionCalls = 221

class BuiltInFunction(IntEnum): 
    EffectTransition = 102 # PARAMS: 1
    PrintStringToConsole = 180 # PARAMS: 1+
    SpatialShow = 202 # PARAMS: 1
    TimePlay = 206 # PARAMS: 1

class OperandType(IntEnum):
    Literal = 151
    String = 154
    # TODO: This only seems to be used in effectTransition:
    #  effectTransition ( $FadeToPalette )
    # compiles to:
    #  [219, 102, 1]
    #  [155, 301]
    DollarSignVariable = 155
    AssetId = 156

# TODO: This is a debugging script to help decompile the bytecode 
# when there are opcodes we have documented but still provide a
# fall-through when there are undocuemnted opcodes.
def cast_to_enum(value, enum_class):
    try:
        return enum_class(value)
    except ValueError:
        return value

## An abstract compiled script that executes in the Media Station bytecode interpreter.
class Script:
    ## TODO: Export these to individual JSONs rather than putting them in the 
    ## main JSON export (that will make analyzing them much easier!)
    def export(self, root_directory_path, command_line_arguments):
        return

## A compiled function that executes in the Media Station bytecode interpreter.
class Function(Script):
    ## Reads a compiled script from a binary stream at is current position.
    ## \param[in] stream - A binary stream that supports the read method.
    def __init__(self, chunk):
        # READ METADATA.
        # The name might be assigned later based on a PROFILE._ST, so we need a
        # place to store it.
        self.name = None
        # The script ID is only populated if the script is in its own chunk.
        # If it is instead attached to an asset header, it takes on the ID of that asset.
        self.id = Datum(chunk).d + 19900
        # TODO: Actually verify the file ID.
        self.file_id = Datum(chunk)

        # READ THE BYTECODE.
        self._code = CodeChunk(chunk.stream)
        print()
        if not global_variables.version.is_first_generation_engine:
            assert_equal(Datum(chunk).d, 0x00, "end-of-chunk flag")

## A compiled event handler that executes in the Media Station bytecode interpreter.
class EventHandler(Script):
    class EventType(IntEnum):
        Time = 0x05, # Timer
        MouseDown = 0x06, # Hotspot
        SoundEnd = 14,
        MovieEnd = 21,

    ## Reads a compiled script from a binary stream at is current position.
    ## \param[in] stream - A binary stream that supports the read method.
    def __init__(self, chunk):
        # READ THE SCRIPT TYPE.
        # This only occurs in scripts that are attached to asset headers.
        # TODO: Understand what this is. I think it says when a given script
        # triggers (like when the asset is clicked, etc.)
        self.type = Datum(chunk).d
        print(f'TYPE: {self.type}')
        self.unk1 = Datum(chunk).d

        # READ THE BYTECODE.
        self.length_in_bytes = Datum(chunk).d
        self._code = CodeChunk(chunk.stream)

## TODO: Is this a whole function, or is it something else?
class CodeChunk:
    def __init__(self, stream, length_in_bytes = None):
        # GET THE LENGTH.
        self._stream = stream
        if not length_in_bytes:
            self._length_in_bytes = Datum(stream).d
        else:
            self._length_in_bytes = length_in_bytes
        self._start_pointer = stream.tell()

        # READ THE BYTECODE.
        self.statements = []
        while not self._at_end:
            statement = self.read_statement(stream)
            pprint.pprint(statement)
            self.statements.append(statement)
        print()

    @property
    def _end_pointer(self):
        return self._start_pointer + self._length_in_bytes

    @property
    def _at_end(self):
        return self._stream.tell() >= self._end_pointer

    # This is a recursive function that builds a statement.
    # Statement probably isn't ths best term, since statements can contain other statements. 
    # And I don't want to imply that it is some sort of atomic thing. 
    ## \param[in] stream - A binary stream at the start of the statement.
    def read_statement(self, stream):
        section_type = Datum(stream)
        if (Datum.Type.UINT32_1 == section_type.t):
            return CodeChunk(stream, section_type.d)

        # Just like in real assembly language, different combinations of opcodes
        # have different available "addressing modes".
        iteratively_built_statement = []
        if InstructionType.FunctionCall == section_type.d:
            opcode = Opcodes(Datum(stream).d)
            if Opcodes.TestEquality == opcode:
                lhs = self.read_statement(stream)
                rhs = self.read_statement(stream)
                statement = [opcode, lhs, rhs]

            elif (Opcodes.GetValue == opcode) or (Opcodes.UnkRelatedToVariableAssignment == opcode):
                variable_id = self.read_statement(stream)
                # TODO: This is the same "4" literal that we see above.
                unk = self.read_statement(stream)
                statement = [opcode, variable_id, unk]

            else:
                # These are always immediates.
                # The scripting language doesn't seem to have
                # support for virtual functions (thankfully).
                function_id = cast_to_enum(Datum(stream).d, BuiltInFunction)
                parameter_count = Datum(stream).d
                statement = [opcode, function_id, parameter_count]
            iteratively_built_statement.extend(statement)

        elif InstructionType.Operand == section_type.d:
            operand_type = OperandType(Datum(stream).d)
            if OperandType.String == operand_type:
                # Note that this is not a datum with a type code 
                # of string. In this case, the operand type is stored 
                # in a datum of its own. So we MUST read the string here
                # and cannot delegate that to the Datum as just another
                # string type.
                string_length = Datum(stream).d
                value = stream.read(string_length).decode('latin-1')

            #elif OperandType.AssetId == operand_type:
            #    value = Datum(stream).d

            else:
                value = self.read_statement(stream)
                
            statement = [operand_type, value]
            iteratively_built_statement.extend(statement)

        elif InstructionType.VariableReference == section_type.d:
            s1 = Datum(stream).d
            s2 = Datum(stream).d
            statement = [s1, s2]
            iteratively_built_statement.extend(statement)

        else:
            iteratively_built_statement = section_type.d

        return iteratively_built_statement

    # TODO: Remove this. It is temporarily kept around for debugging purposes,
    # as it gives a lower-level view into what strings we're seeing.
    def read_statement_debugging_version(self, stream):
        iteratively_built_statement = []
        while not self._at_end:
            statement = self.read_datum_maybe_string(stream)
            if isinstance(statement, CodeChunk):
                statement = statement.statements
            iteratively_built_statement.append(statement)
        pprint.pprint(iteratively_built_statement)
        return iteratively_built_statement

    # TODO: Remove this. It is temporarily kept around for debugging purposes,
    # as it gives a lower-level view into what strings we're seeing.
    def read_datum_maybe_string(self, stream):
        statement = Datum(stream)
        if (Datum.Type.UINT32_1 == statement.t):
            return CodeChunk(stream, statement.d)
        if statement.d == 0x009a:
            string_length = Datum(stream).d
            statement = stream.read(string_length).decode('latin-1')
            print(f'> {statement}')
            return statement
        else:
            return statement.d