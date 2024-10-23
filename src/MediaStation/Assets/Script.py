from dataclasses import dataclass
from enum import IntEnum
import pprint
import os

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
    IfElse = 202
    AssignVariable = 203
    Or = 204
    And = 206
    Equals = 207
    NotEquals = 208
    LessThan = 209
    GreaterThan = 210
    LessThanOrEqualTo = 211
    GreaterThanOrEqualTo = 212
    Add = 213
    Subtract = 214
    Divide = 216
    Modulo = 217
    Unk2 = 218 # TODO: Likely something with ## constants like ##DOWN?
    CallRoutine = 219
    # Method calls are like routine calls, but they have an implicit "self"
    # parameter that is always the first. For example:
    #  @self . mouseActivate ( TRUE ) ;
    CallMethod = 220
    # This seems to appear at the start of a function to declare the number of
    # local variables used in the function. It seems to be the `Declare`
    # keyword. In the observed examples, the number of variables to create is
    # given, then the next instructions are variable assignments for that number
    # of variables.
    DeclareVariables = 221
    While = 224
    Return = 222

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
    spatialHide = 203 # PARAMS: 1
    spatialMoveTo = 204 # PARAMS: 2
    # spatialZMoveTo
    spatialShow = 202 # PARAMS: 1
    timePlay = 206 # PARAMS: 1
    timeStop = 207 # PARAMS: 0
    isPlaying = 372
    # debugBeep
    # quit
    # DebugPrint

    # HOTSPOT METHODS.
    mouseActivate = 210 # PARAMS: 1
    mouseDeactivate = 211 # PARAMS: 0
    xPosition = 233 # PARAMS: 0
    yPosiion = 234 # PARAMS: 0
    TriggerAbsXPosition = 321 # PARAMS: 0
    TriggerAbsYPosition = 322 # PARAMS: 0
    isActive = 371 # PARAMS: 0

    # IMAGE METHODS.
    Width = 235 # PARAMS: 0
    Height = 236 # PARAMS: 0
    # isVisible

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

    # CANVAS METHODS.
    clearToPalette = 379 # PARAMS: 1

    # DOCUMENT METHODS.
    loadContext = 374 # PARAMS: 1
    releaseContext = 375 # PARAMS: 1
    branchToScreen = 201 # PARAMS: 1
    isLoaded = 376 # PARAMS: 1

    # PATH METHODS.
    percentComplete = 263

    # TEXT METHODS.
    text = 290
    setText = 291
    setMaximumTextLength = 293 # PARAM: 1

    # COLLECTION METHODS.
    # These aren't assets but arrays used in Media Script.
    # isEmpty
    empty = 252 # PARAMS: 0
    append = 247 # PARAMS: 1+
    getAt = 253 # PARAMS: 1
    count = 249 # PARAMS: 0
    # Looks like this lets you call a method on all the items in a collection.
    # Examples look like : var_7be1_collect_shapes.send(spatialHide);
    send = 257 # PARAMS: 1+. Looks like the first param is the function, 
               # and the next params are any arguments you want to send.
    # Seeking seems to be finding the index where a certain item is.
    seek = 256 # PARAMS: 1
    sort = 266 # PARAMS: 0
    deleteAt = 258 # PARAMS: 1 

    # PRINTER METHODS.
    openLens = 346 # PARAMS: 0
    closeLens = 347 # PARAMS: 0

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
    VariableType = 158
    Function = 160

class VariableScope(IntEnum):
    Local = 1
    Parameter = 2
    Global = 4

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

## A compiled function that executes in the Media Station bytecode interpreter.
class Function:
    ## Reads a compiled script from a binary stream at is current position.
    ## \param[in] stream - A binary stream that supports the read method.
    def __init__(self, chunk):
        # READ METADATA.
        # The name might be assigned later based on a PROFILE._ST, so we need a
        # place to store it.
        self.name = None
        # TODO: Actually verify the file ID.
        self.file_id = Datum(chunk)
        # The script ID is only populated if the script is in its own chunk.
        # If it is instead attached to an asset header, it takes on the ID of that asset.
        # Functions with low ID numbers are "built-in" functions, and 
        # functions with large ID numbers are user-defined functions.
        self.id = Datum(chunk).d + 19900

        # READ THE BYTECODE.
        self._code = CodeChunk(chunk.stream)
        if not global_variables.version.is_first_generation_engine:
            assert_equal(Datum(chunk).d, 0x00, "end-of-chunk flag")

    def export(self, root_directory_path, command_line_arguments):
        if self.name is None:
            self.name = self.id
        script_dump_filename = f"{self.name}_script.txt"
        script_dump_filepath = os.path.join(root_directory_path, script_dump_filename)
        global_variables.application.logger.debug(f'Dumping function to {script_dump_filepath}')
        with open(script_dump_filepath, 'w') as script_dump_file:
            for statement in self._code.statements:
                script_dump_file.write(pprint.pformat(statement) + '\n')

## A compiled event handler that executes in the Media Station bytecode interpreter.
class EventHandler:
    class Type(IntEnum):
        # TIMER EVENTS.
        Time = 5

        # HOTSPOT EVENTS.
        MouseDown = 6
        MouseUp = 7
        MouseMoved = 8
        MouseEntered = 9
        MouseExited = 10
        KeyDown = 13 # PARAMS: 1 - ASCII code.

        # SOUND EVENTS.
        SoundEnd = 14
        SoundAbort = 19
        SoundFailure = 20
        SoundStopped = 29

        # MOVIE EVENTS.
        MovieBegin = 32
        MovieFailure = 22
        MovieAbort = 21
        MovieEnd = 15
        MovieStopped = 31

        # SPRITE EVENTS.
        # Just "MovieEnd" in source.
        SpriteMovieEnd = 23

        # SCREEN EVENTS.
        Entry = 17
        Exit = 27

        # CONTEXT EVENTS. 
        LoadComplete = 44 # PARAMS: 1 - Context ID

        # TEXT EVENTS.
        Input = 37 # Text
        Error = 38 # Text

        # CAMERA EVENTS.
        PanAbort = 43
        PanEnd = 42

        # PATH EVENTS.
        Step = 28
        PathStopped = 33
        PathEnd = 16

    class ArgumentType(IntEnum):
        # There is still an argument value provided when it's null, 
        # it might well be the number of bytes in the bytecode. It doens't seem
        # to be constant.
        Null = 0
        AsciiCode = 1 # TODO: Why is this datum type a float?
        Time = 3
        Context = 5 # LoadComplete

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

        # READ THE ARGUMENT.
        # Some event handlers seem to take exactly one "argument" that specifies
        # the event further. The exact meaning depends on the event type. The following
        # types have been observed:
        #  - On LoadComplete "context_e1" (Context)
        #    "context_e1" is the argument, and it is the name of a screen (context). In
        #    the bytecode, it is the ID of that context.
        #
        #  - On KeyDown "\r" (Hotspot)
        #    A keydown of 0 seems to indicate ANY key down will trigger the
        #    event. Not sure yet if this includes 
        #
        #  - On Time 00:10.00 (Timer)
        #    The argument here is the time value, which is stored in the
        #    bytecode as a float of seconds.
        # Seems like there is some "syntaxtic sugar" to be able to specify
        # multiple events in a single block. For example:
        #   On SoundFailure
		#   On SoundAbort
        #    ...
		#   End
        # 
        # Or even the same event type with different params:
        #   On KeyDown "A"
		#   On KeyDown "B"
        #    ...
		#   End
        #  
        # In these cases, a separate event handler seems to be created for each
        # event, and the bytecode is the same between them.
        self.argument_type = maybe_cast_to_enum(Datum(chunk).d, EventHandler.ArgumentType)
        self.argument = Datum(chunk).d

        # READ THE BYTECODE.
        self._code = CodeChunk(chunk.stream)

        # PRINT THE DBEUG STATEMENTS.
        for statement in self._code.statements:
            pprint_debug(statement)

    def export(self, root_directory_path, command_line_arguments):
        # GET THE CORRECT EVENT NAME.
        # This gives the event name if we know it, otherwise just the number.
        script_dump_filename = f"event_{self.type.name if hasattr(self.type, 'name') else self.type}_{self.argument}.txt"

        # EXPORT THE SCRIPT.
        script_dump_filepath = os.path.join(root_directory_path, script_dump_filename)
        global_variables.application.logger.debug(f'Dumping event handler to {script_dump_filepath}')
        with open(script_dump_filepath, 'w') as script_dump_file:
            # TODO: Write the argument type.
            script_dump_file.write(f'ARGUMENT: {self.argument} (type: {self.argument_type.name if hasattr(self.argument, "name") else self.argument_type})\n')
            for statement in self._code.statements:
                script_dump_file.write(pprint.pformat(statement) + '\n')

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
        # TODO: Find a better way to figure out if we are expecting a code chunk. 
        maybe_instruction_type_maybe_code_chunk_length = Datum(stream)
        if (Datum.Type.UINT32_1 == maybe_instruction_type_maybe_code_chunk_length.t):
            return CodeChunk(stream, length_in_bytes = maybe_instruction_type_maybe_code_chunk_length.d).statements

        # Just like in real assembly language, different combinations of opcodes
        # have different available "addressing modes".
        instruction_type = maybe_instruction_type_maybe_code_chunk_length.d
        iteratively_built_statement = []
        if InstructionType.FunctionCall == instruction_type:
            instruction_type = maybe_cast_to_enum(maybe_instruction_type_maybe_code_chunk_length.d, InstructionType)
            opcode = maybe_cast_to_enum(Datum(stream).d, Opcodes)
            if Opcodes.IfElse == opcode:
                values_to_compare = self.read_statement(stream)
                code_if_true = self.read_statement(stream)
                code_if_false = self.read_statement(stream)
                statement = [instruction_type, opcode, values_to_compare, code_if_true, code_if_false]

            elif Opcodes.While == opcode:
                condition = self.read_statement(stream)
                code = self.read_statement(stream)
                statement = [instruction_type, opcode, condition, code]

            elif Opcodes.Return == opcode:
                value = self.read_statement(stream)
                statement = [instruction_type, opcode, value]

            elif Opcodes.Unk2 == opcode:
                lhs = self.read_statement(stream)
                statement = [instruction_type, opcode, lhs]

            elif (Opcodes.Equals == opcode) or \
                (Opcodes.NotEquals == opcode) or \
                (Opcodes.Add == opcode) or \
                (Opcodes.Subtract == opcode) or \
                (Opcodes.Divide == opcode) or \
                (Opcodes.Modulo == opcode) or \
                (Opcodes.And == opcode) or \
                (Opcodes.Or == opcode) or \
                (Opcodes.LessThan == opcode) or \
                (Opcodes.LessThanOrEqualTo == opcode) or \
                (Opcodes.GreaterThan == opcode) or \
                (Opcodes.GreaterThanOrEqualTo == opcode):
                lhs = self.read_statement(stream)
                rhs = self.read_statement(stream)
                statement = [instruction_type, opcode, lhs, rhs]

            elif Opcodes.AssignVariable == opcode:
                variable_id = self.read_statement(stream)
                variable_scope = maybe_cast_to_enum(self.read_statement(stream), VariableScope)
                new_value = self.read_statement(stream)
                statement = [instruction_type, opcode, variable_id, variable_scope, new_value]

            elif Opcodes.DeclareVariables == opcode:
                count = self.read_statement(stream)
                statement = [instruction_type, opcode, count]

            elif (Opcodes.CallRoutine == opcode):
                # These are always immediates.
                # The scripting language doesn't seem to have
                # support for virtual functions (thankfully).
                function_id = maybe_cast_to_enum(Datum(stream).d, BuiltInFunction)
                parameter_count = Datum(stream).d
                params = [self.read_statement(stream) for _ in range(parameter_count)]
                statement = [instruction_type, opcode, function_id, parameter_count, params]

            elif (Opcodes.CallMethod == opcode):
                # These are always immediates.
                # The scripting language doesn't seem to have
                # support for virtual functions (thankfully).
                function_id = maybe_cast_to_enum(Datum(stream).d, BuiltInFunction)
                parameter_count = Datum(stream).d
                this = self.read_statement(stream)
                params = [self.read_statement(stream) for _ in range(parameter_count)]
                statement = [instruction_type, opcode, function_id, parameter_count, this, params]

            else:
                unk1 = Datum(stream).d
                unk2 = Datum(stream).d
                statement = [instruction_type, opcode, unk1, unk2]

            iteratively_built_statement.extend(statement)

        elif InstructionType.Operand == instruction_type:
            instruction_type = maybe_cast_to_enum(maybe_instruction_type_maybe_code_chunk_length.d, InstructionType)
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

            elif OperandType.Function == operand_type:
                # TODO: Can we replace this with just a datum? Is there any
                # instance where the function is an expression?
                value = maybe_cast_to_enum(self.read_statement(stream), BuiltInFunction)

            else:
                value = self.read_statement(stream)
                
            statement = [instruction_type, operand_type, value]
            iteratively_built_statement.extend(statement)

        elif InstructionType.VariableReference == instruction_type:
            instruction_type = maybe_cast_to_enum(maybe_instruction_type_maybe_code_chunk_length.d, InstructionType)
            variable_id = Datum(stream).d
            variable_scope = maybe_cast_to_enum(Datum(stream).d, VariableScope)
            statement = [instruction_type, variable_id, variable_scope]
            iteratively_built_statement.extend(statement)

        else:
            iteratively_built_statement = instruction_type

        return iteratively_built_statement
