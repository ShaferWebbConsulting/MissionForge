/*
 * telemetry_client.cpp
 *
 * Legacy TAO CORBA Telemetry Client / Bridge
 * Connects to the legacy TelemetryService via CORBA and reads telemetry.
 * In TAO mode: uses the real CORBA IOR to invoke getLatestTelemetry().
 * In mock mode: reads JSON lines from stdin (piped from telemetry_server).
 *
 * The bridge forwards each telemetry sample as a JSON event to the
 * MissionForge adapter via HTTP POST.
 *
 * Build: see CMakeLists.txt
 * Usage (mock): ./telemetry_server | ./telemetry_client
 * Usage (TAO):  ./telemetry_client -ORBInitRef TelemetryService=file:///tmp/TelemetryService.ior
 */

#include <iostream>
#include <fstream>
#include <sstream>
#include <string>
#include <thread>
#include <chrono>
#include <cstring>

#ifdef USE_TAO_ORB
  #include <tao/corba.h>
  #include "TelemetryC.h"  // Generated stub from Telemetry.idl
#endif

/* -----------------------------------------------------------------------
 * Minimal HTTP POST helper (no external deps — plain POSIX sockets)
 * Sends a JSON body to the MissionForge adapter endpoint.
 * --------------------------------------------------------------------- */
#ifdef __linux__
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <netdb.h>
#include <unistd.h>

static bool http_post(const std::string& host, int port,
                      const std::string& path, const std::string& json_body) {
    struct addrinfo hints{}, *res = nullptr;
    hints.ai_family   = AF_INET;
    hints.ai_socktype = SOCK_STREAM;
    std::string port_str = std::to_string(port);
    if (getaddrinfo(host.c_str(), port_str.c_str(), &hints, &res) != 0)
        return false;

    int fd = socket(res->ai_family, res->ai_socktype, res->ai_protocol);
    if (fd < 0) { freeaddrinfo(res); return false; }
    if (connect(fd, res->ai_addr, res->ai_addrlen) != 0) {
        close(fd); freeaddrinfo(res); return false;
    }
    freeaddrinfo(res);

    std::ostringstream req;
    req << "POST " << path << " HTTP/1.0\r\n"
        << "Host: " << host << ":" << port << "\r\n"
        << "Content-Type: application/json\r\n"
        << "Content-Length: " << json_body.size() << "\r\n"
        << "Connection: close\r\n\r\n"
        << json_body;
    std::string r = req.str();
    send(fd, r.c_str(), r.size(), 0);

    // Drain response (ignore body)
    char buf[512];
    while (recv(fd, buf, sizeof(buf), 0) > 0) {}
    close(fd);
    return true;
}
#else
// Windows stub — extend as needed
static bool http_post(const std::string&, int, const std::string&, const std::string&) {
    return false;
}
#endif

/* -----------------------------------------------------------------------
 * Configuration (override via environment variables)
 * --------------------------------------------------------------------- */
static std::string adapter_host() {
    const char* h = getenv("ADAPTER_HOST");
    return h ? h : "missionforge-adapter";
}
static int adapter_port() {
    const char* p = getenv("ADAPTER_PORT");
    return p ? std::stoi(p) : 8000;
}

/* -----------------------------------------------------------------------
 * Mock mode: read JSON lines from stdin, forward each to adapter
 * --------------------------------------------------------------------- */
static int mock_bridge_main() {
    std::cerr << "[BRIDGE] Mock mode — forwarding JSON from stdin to "
              << adapter_host() << ":" << adapter_port() << std::endl;
    std::string line;
    while (std::getline(std::cin, line)) {
        if (line.empty() || line[0] != '{') continue;
        bool ok = http_post(adapter_host(), adapter_port(),
                            "/internal/telemetry", line);
        if (!ok) {
            std::cerr << "[BRIDGE] Warning: failed to forward to adapter" << std::endl;
        } else {
            std::cerr << "[BRIDGE] Forwarded: " << line.substr(0, 60) << "..." << std::endl;
        }
    }
    return 0;
}

/* -----------------------------------------------------------------------
 * TAO mode: poll CORBA service, serialize to JSON, forward to adapter
 * --------------------------------------------------------------------- */
#ifdef USE_TAO_ORB
static int tao_bridge_main(int argc, char* argv[]) {
    try {
        CORBA::ORB_var orb = CORBA::ORB_init(argc, argv, "TAO");
        CORBA::Object_var obj =
            orb->resolve_initial_references("TelemetryService");
        MissionSystem::TelemetryService_var svc =
            MissionSystem::TelemetryService::_narrow(obj.in());
        if (CORBA::is_nil(svc.in())) {
            std::cerr << "[BRIDGE-TAO] Could not narrow TelemetryService" << std::endl;
            return 1;
        }
        std::cerr << "[BRIDGE-TAO] Connected to TelemetryService via CORBA" << std::endl;

        while (true) {
            MissionSystem::TelemetryData_var td = svc->getLatestTelemetry();

            const char* ss = "OK";
            if (td->sensor_status == MissionSystem::SENSOR_DEGRADED) ss = "DEGRADED";
            if (td->sensor_status == MissionSystem::SENSOR_FAILED)   ss = "FAILED";

            std::ostringstream json;
            json << std::fixed << std::setprecision(2)
                 << "{\"engine_temp\":"  << td->engine_temp
                 << ",\"vibration\":"    << td->vibration
                 << ",\"fuel_flow\":"    << td->fuel_flow
                 << ",\"oil_pressure\":" << td->oil_pressure
                 << ",\"cpu_usage\":"    << td->cpu_usage
                 << ",\"memory_usage\":" << td->memory_usage
                 << ",\"sensor_status\":\"" << ss << "\""
                 << ",\"timestamp\":\""  << td->timestamp.in() << "\""
                 << "}";

            http_post(adapter_host(), adapter_port(),
                      "/internal/telemetry", json.str());
            std::this_thread::sleep_for(std::chrono::seconds(1));
        }
        orb->destroy();
    } catch (const CORBA::Exception& e) {
        std::cerr << "[BRIDGE-TAO] CORBA exception: " << e._info().c_str() << std::endl;
        return 1;
    }
    return 0;
}
#endif

int main(int argc, char* argv[]) {
#ifdef USE_TAO_ORB
    return tao_bridge_main(argc, argv);
#else
    return mock_bridge_main();
#endif
}
