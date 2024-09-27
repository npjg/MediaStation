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
    And = 206
    Equals = 207
    NotEquals = 208
    LessThan = 209
    GreaterThan = 210
    Add = 213
    Subtract = 214
    Divide = 216
    Unk2 = 218
    # Routine calls have this form:
    #  [Opcode.CallRoutine, FunctionId, ParametersCount]
    # Followed by the actual parameters to pass to the function.
    # Functions with low ID numbers are "built-in" functions, and 
    # functions with large ID numbers are user-defined functions.
    CallRoutine = 219
    # Method calls are like function calls, but they have an implicit "self"
    # parameter that is always the first. For example:
    #  @self . mouseActivate ( TRUE ) ;
    # compiles to:
    #  [220, 210, 0] - [Opcode.CallMethod, BuiltInFunction.MouseActivate, 0 parameters]
    #  [156, 123]    - [OperandType.AssetId, 123 (asset ID for self - this is pre-computed)]
    #  [151, 1]      - [OperandType.Literal, 1 (literal for TRUE)]
    CallMethod = 220
    UnkSomethingWithFunctionCalls = 221 # Probably Assign Collection?

class BuiltInFunction(IntEnum): 
    # TODO: Split out routines and methods into different enums.
    # ROUTINES.
    # effectTransitionOnSync = 13 # PARAMS: 1
    drawing = 37 # PARAMS: 5
    EffectTransition = 102 # PARAMS: 1
    PrintStringToConsole = 180 # PARAMS: 1+
    # TODO: What object types does CursorSet apply to?
    # Currently it's only in var_7be1_cursor_currentTool in
    # IBM/Crayola.
    cursorSet = 200 # PARAMS: 0
    SpatialShow = 202 # PARAMS: 1
    TimePlay = 206 # PARAMS: 1
    TimeStop = 207 # PARAMS: 0

    # HOTSPOT METHODS.
    mouseActivate = 210 # PARAMS: 1
    mouseDeactivate = 211 # PARAMS: 0
    xPosition = 233 # PARAMS: 0
    yPosiion = 234 # PARAMS: 0
    TriggerAbsXPosition = 321 # PARAMS: 0
    TriggerAbsYPosition = 322 # PARAMS: 0

    # IMAGE METHODS.
    Width = 235 # PARAMS: 0
    Height = 236 # PARAMS: 0

    # SPRITE METHODS.
    movieReset = 219 # PARAMS: 0

    # STAGE METHODS.
    setWorldSpaceExtent = 363 # PARAMS: 2
    setBounds = 287 # PARAMS: 4

    # CAMERA METHODS.
    stopPan = 350 # PARAMS: 0
    viewportMoveTo = 352 # PARAMS: 2    
    yViewportPosition = 357 # PARAMS: 0
    panTo = 370 # PARAMS: 4

class OperandType(IntEnum):
    # TODO: Figure out the difference between these two.
    Literal = 151
    Literal2 = 153
    String = 154
    # TODO: This only seems to be used in effectTransition:
    #  effectTransition ( $FadeToPalette )
    # compiles to:
    #  [219, 102, 1]
    #  [155, 301]
    DollarSignVariable = 155
    AssetId = 156
    Float = 157

# TODO: This is a debugging script to help decompile the bytecode 
# when there are opcodes we have documented but still provide a
# fall-through when there are undocuemnted opcodes.
def maybe_cast_to_enum(value, enum_class):
    try:
        return enum_class(value)
    except ValueError:
        global_variables.application.logger.debug(f'SCRIPT WARN: Failed to cast {value} to {enum_class}')
        return value

def pprint_debug(object):
    if isinstance(object, CodeChunk):
        global_variables.application.logger.debug("-- CHUNK --")
        pprint_debug(object.statements)
    else:
        debugging_string = pprint.pformat(object)
        global_variables.application.logger.debug(debugging_string)

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
        if not global_variables.version.is_first_generation_engine:
            assert_equal(Datum(chunk).d, 0x00, "end-of-chunk flag")

## A compiled event handler that executes in the Media Station bytecode interpreter.
class EventHandler(Script):
    class Type(IntEnum):
        Time = 0x05 # Timer
        MouseDown = 0x06 # Hotspot
        MouseMoved = 0x08 # Hotspot
        MouseEntered = 9 # Hotspot
        MouseExited = 10 # Hotspot
        KeyDown = 13 # TODO: Where is the key actually stored?
        SoundEnd = 14
        SoundFailure = 20 # Sound
        SoundAbort = 19 # Sound
        MovieEnd = 21
        Entry = 17 # Screen
        Exit = 27 # Screen
        PanAbort = 43 # Camera
        PanEnd = 42 # Camera

    ## Reads a compiled script from a binary stream at is current position.
    ## \param[in] stream - A binary stream that supports the read method.
    def __init__(self, chunk):
        # READ THE SCRIPT TYPE.
        # This only occurs in scripts that are attached to asset headers.
        # TODO: Understand what this is. I think it says when a given script
        # triggers (like when the asset is clicked, etc.)
        self.type = maybe_cast_to_enum(Datum(chunk).d, EventHandler.Type)
        global_variables.application.logger.debug("*************** EVENT HANDLER ***************")
        global_variables.application.logger.debug(f'Event Handler TYPE: {self.type.__repr__()}')
        self.unk1 = Datum(chunk).d
        global_variables.application.logger.debug(f'Unk1: {self.unk1}')

        # READ THE BYTECODE.
        self.length_in_bytes = Datum(chunk).d
        self._code = CodeChunk(chunk.stream)

        # PRINT THE DBEUG STATEMENTS.
        for statement in self._code.statements:
            pprint_debug(statement)
            
## TODO: Is this a whole function, or is it something else?
class CodeChunk:
    def __init__(self, stream, length_in_bytes = None):
        # GET THE LENGTH.
        self._stream = stream
        if not length_in_bytes:
            self._length_in_bytes = Datum(stream).d
        else:
            self._length_in_bytes = length_in_bytes
        self._start_offset = stream.tell()

        # READ THE BYTECODE.
        self.statements = []
        while not self._at_end:
            statement = self.read_statement(stream)
            self.statements.append(statement)

    @property
    def _end_offset(self):
        return self._start_offset + self._length_in_bytes

    @property
    def _at_end(self):
        return self._stream.tell() >= self._end_offset

    # This is a recursive function that builds a statement.
    # Statement probably isn't ths best term, since statements can contain other statements. 
    # And I don't want to imply that it is some sort of atomic thing. 
    ## \param[in] stream - A binary stream at the start of the statement.
    def read_statement(self, stream):
        instruction_type = Datum(stream)
        if (Datum.Type.UINT32_1 == instruction_type.t):
            return CodeChunk(stream, instruction_type.d).statements

        # Just like in real assembly language, different combinations of opcodes
        # have different available "addressing modes".
        iteratively_built_statement = []
        if InstructionType.FunctionCall == instruction_type.d:
            opcode = maybe_cast_to_enum(Datum(stream).d, Opcodes)
            if Opcodes.TestEquality == opcode:
                values_to_compare = self.read_statement(stream)
                code_if_true = self.read_statement(stream)
                code_if_false = self.read_statement(stream)
                statement = [opcode, values_to_compare, code_if_true, code_if_false]

            elif Opcodes.Unk2 == opcode:
                lhs = self.read_statement(stream)
                statement = [opcode, lhs]

            elif (Opcodes.Equals == opcode) or \
                (Opcodes.NotEquals == opcode) or \
                (Opcodes.Add == opcode) or \
                (Opcodes.Subtract == opcode) or \
                (Opcodes.Divide == opcode) or \
                (Opcodes.And == opcode) or \
                (Opcodes.LessThan == opcode) or \
                (Opcodes.GreaterThan == opcode):
                lhs = self.read_statement(stream)
                rhs = self.read_statement(stream)
                statement = [opcode, lhs, rhs]

            elif Opcodes.AssignVariable == opcode:
                variable_id = self.read_statement(stream)
                # TODO: This is the same "4" literal that we see above.
                # Maybe this is a variable scope, like local, screen, or global?
                unk = self.read_statement(stream)
                new_value = self.read_statement(stream)
                statement = [opcode, variable_id, unk, new_value]

            elif (Opcodes.CallRoutine == opcode):
                # These are always immediates.
                # The scripting language doesn't seem to have
                # support for virtual functions (thankfully).
                function_id = maybe_cast_to_enum(Datum(stream).d, BuiltInFunction)
                parameter_count = Datum(stream).d
                params = [self.read_statement(stream) for _ in range(parameter_count)]
                statement = [opcode, function_id, parameter_count, params]

            elif (Opcodes.CallMethod == opcode):
                # These are always immediates.
                # The scripting language doesn't seem to have
                # support for virtual functions (thankfully).
                function_id = maybe_cast_to_enum(Datum(stream).d, BuiltInFunction)
                parameter_count = Datum(stream).d
                this = self.read_statement(stream)
                params = [self.read_statement(stream) for _ in range(parameter_count)]
                statement = [opcode, function_id, parameter_count, this, params]

            else:
                unk1 = Datum(stream).d
                unk2 = Datum(stream).d
                statement = [opcode, unk1, unk2]

            iteratively_built_statement.extend(statement)

        elif InstructionType.Operand == instruction_type.d:
            operand_type = maybe_cast_to_enum(Datum(stream).d, OperandType)
            if OperandType.String == operand_type:
                # Note that this is not a datum with a type code 
                # of string. In this case, the operand type is stored 
                # in a datum of its own. So we MUST read the string here
                # and cannot delegate that to the Datum as just another
                # string type.
                string_length = Datum(stream).d
                value = stream.read(string_length).decode('latin-1')

            elif OperandType.AssetId == operand_type:
                value = Datum(stream).d

            else:
                value = self.read_statement(stream)
                
            statement = [operand_type, value]
            iteratively_built_statement.extend(statement)

        elif InstructionType.VariableReference == instruction_type.d:
            s1 = Datum(stream).d
            s2 = Datum(stream).d
            statement = [s1, s2]
            iteratively_built_statement.extend(statement)

        else:
            iteratively_built_statement = instruction_type.d

        return iteratively_built_statement
