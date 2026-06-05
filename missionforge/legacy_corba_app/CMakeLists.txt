cmake_minimum_required(VERSION 3.16)
project(LegacyCORBATelemetry CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# -------------------------------------------------------------------------
# Optional TAO ORB support
# Set -DUSE_TAO_ORB=ON to compile against real TAO/ACE libraries.
# Default: OFF (mock mode — no TAO dependency required).
# -------------------------------------------------------------------------
option(USE_TAO_ORB "Compile against TAO ORB / ACE" OFF)

if(USE_TAO_ORB)
    # Locate ACE/TAO — adjust paths to your installation
    find_path(ACE_INCLUDE_DIR ace/ACE.h
        HINTS /usr/local/include /usr/include
              $ENV{ACE_ROOT}/include $ENV{ACE_ROOT})
    find_path(TAO_INCLUDE_DIR tao/corba.h
        HINTS /usr/local/include /usr/include
              $ENV{TAO_ROOT}/include $ENV{TAO_ROOT})
    find_library(ACE_LIBRARY NAMES ACE
        HINTS /usr/local/lib /usr/lib $ENV{ACE_ROOT}/lib)
    find_library(TAO_LIBRARY NAMES TAO
        HINTS /usr/local/lib /usr/lib $ENV{TAO_ROOT}/lib)
    find_library(TAO_PORTABLESERVER_LIBRARY NAMES TAO_PortableServer
        HINTS /usr/local/lib /usr/lib $ENV{TAO_ROOT}/lib)

    if(ACE_INCLUDE_DIR AND TAO_INCLUDE_DIR AND ACE_LIBRARY AND TAO_LIBRARY)
        message(STATUS "TAO ORB found — building with CORBA support")
        add_compile_definitions(USE_TAO_ORB)
        set(TAO_INCLUDES ${ACE_INCLUDE_DIR} ${TAO_INCLUDE_DIR})
        set(TAO_LIBS ${TAO_LIBRARY} ${TAO_PORTABLESERVER_LIBRARY} ${ACE_LIBRARY})

        # Generate CORBA stubs/skeletons from IDL
        # (tao_idl must be in PATH; adjust as needed)
        set(IDL_FILE ${CMAKE_SOURCE_DIR}/idl/Telemetry.idl)
        add_custom_command(
            OUTPUT TelemetryC.cpp TelemetryC.h TelemetryS.cpp TelemetryS.h
            COMMAND tao_idl -I${TAO_INCLUDE_DIR} ${IDL_FILE}
            DEPENDS ${IDL_FILE}
            COMMENT "Generating TAO CORBA stubs/skeletons from Telemetry.idl"
        )
        set(GENERATED_SOURCES TelemetryC.cpp TelemetryS.cpp)
    else()
        message(WARNING "TAO ORB not found — falling back to mock mode")
        set(USE_TAO_ORB OFF)
        set(GENERATED_SOURCES "")
        set(TAO_INCLUDES "")
        set(TAO_LIBS "")
    endif()
else()
    message(STATUS "Building in mock mode (no TAO ORB dependency)")
    set(GENERATED_SOURCES "")
    set(TAO_INCLUDES "")
    set(TAO_LIBS "")
endif()

# -------------------------------------------------------------------------
# Telemetry Server
# -------------------------------------------------------------------------
add_executable(telemetry_server
    src/telemetry_server.cpp
    ${GENERATED_SOURCES}
)
target_include_directories(telemetry_server PRIVATE
    ${CMAKE_BINARY_DIR}
    ${TAO_INCLUDES}
)
target_link_libraries(telemetry_server PRIVATE ${TAO_LIBS})
if(UNIX)
    target_link_libraries(telemetry_server PRIVATE pthread)
endif()

# -------------------------------------------------------------------------
# Telemetry Client / Bridge
# -------------------------------------------------------------------------
add_executable(telemetry_client
    src/telemetry_client.cpp
    ${GENERATED_SOURCES}
)
target_include_directories(telemetry_client PRIVATE
    ${CMAKE_BINARY_DIR}
    ${TAO_INCLUDES}
)
target_link_libraries(telemetry_client PRIVATE ${TAO_LIBS})
if(UNIX)
    target_link_libraries(telemetry_client PRIVATE pthread)
endif()

install(TARGETS telemetry_server telemetry_client
        RUNTIME DESTINATION bin)
