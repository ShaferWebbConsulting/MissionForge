/*
 * telemetry_server.cpp
 *
 * Legacy TAO CORBA Telemetry Server
 * Simulates a legacy 32-bit mission computer that continuously publishes
 * aircraft/mission telemetry over CORBA. This server is NEVER modified by
 * MissionForge — it is observed externally.
 *
 * Build: see CMakeLists.txt
 * Usage: ./telemetry_server -ORBEndpoint iiop://localhost:12345
 */

#include <iostream>
#include <cmath>
#include <ctime>
#include <cstring>
#include <sstream>
#include <iomanip>
#include <thread>
#include <chrono>
#include <atomic>
#include <mutex>

// TAO / ACE headers (available when compiled with TAO ORB)
#ifdef USE_TAO_ORB
  #include <tao/corba.h>
  #include <tao/PortableServer/PortableServer.h>
  #include "TelemetryS.h"   // Generated skeleton from Telemetry.idl
#endif

/* -----------------------------------------------------------------------
 * Telemetry state — shared between the simulation thread and CORBA servant
 * --------------------------------------------------------------------- */

struct TelemetryState {
    double engine_temp   = 185.0;
    double vibration     = 0.15;
    double fuel_flow     = 82.0;
    double oil_pressure  = 44.0;
    double cpu_usage     = 35.0;
    double memory_usage  = 55.0;
    std::string sensor_status = "OK";
    std::string timestamp;

    // Fault injection flags set externally via named pipe / file
    bool fault_active    = false;
    int  fault_step      = 0;
};

static TelemetryState g_state;
static std::mutex     g_mutex;
static std::atomic<bool> g_running{true};

/* -----------------------------------------------------------------------
 * ISO-8601 UTC timestamp helper
 * --------------------------------------------------------------------- */
static std::string utc_now() {
    auto now  = std::chrono::system_clock::now();
    auto time = std::chrono::system_clock::to_time_t(now);
    std::tm  tm_buf{};
#ifdef _WIN32
    gmtime_s(&tm_buf, &time);
#else
    gmtime_r(&time, &tm_buf);
#endif
    std::ostringstream ss;
    ss << std::put_time(&tm_buf, "%Y-%m-%dT%H:%M:%SZ");
    return ss.str();
}

/* -----------------------------------------------------------------------
 * Simulation thread — advances telemetry every second
 * --------------------------------------------------------------------- */
static void simulation_thread() {
    while (g_running.load()) {
        std::this_thread::sleep_for(std::chrono::seconds(1));
        std::lock_guard<std::mutex> lock(g_mutex);

        // Check for fault injection signal file
        FILE* f = fopen("/tmp/missionforge_fault", "r");
        if (f) {
            g_state.fault_active = true;
            fclose(f);
        }
        FILE* r = fopen("/tmp/missionforge_reset", "r");
        if (r) {
            g_state.fault_active = false;
            g_state.fault_step   = 0;
            fclose(r);
            remove("/tmp/missionforge_fault");
            remove("/tmp/missionforge_reset");
        }

        if (g_state.fault_active) {
            // Gradual degradation profile
            g_state.fault_step++;
            g_state.engine_temp  += 3.5 + 0.5 * std::sin(g_state.fault_step * 0.3);
            g_state.vibration    += 0.04 + 0.01 * (g_state.fault_step % 3);
            g_state.oil_pressure -= 0.8 + 0.2 * std::cos(g_state.fault_step * 0.2);
            g_state.fuel_flow    -= 0.3;
        } else {
            // Normal fluctuation around baseline
            double t = static_cast<double>(g_state.fault_step) * 0.1;
            g_state.engine_temp  = 185.0 + 5.0  * std::sin(t);
            g_state.vibration    = 0.15  + 0.05 * std::cos(t * 1.3);
            g_state.fuel_flow    = 82.0  + 2.0  * std::sin(t * 0.7);
            g_state.oil_pressure = 44.0  + 2.0  * std::cos(t * 0.9);
            g_state.cpu_usage    = 35.0  + 8.0  * std::sin(t * 1.1);
            g_state.memory_usage = 55.0  + 5.0  * std::cos(t * 0.5);
            g_state.fault_step++;
        }

        // Clamp realistic bounds
        g_state.engine_temp  = std::max(20.0,  g_state.engine_temp);
        g_state.vibration    = std::max(0.0,   g_state.vibration);
        g_state.oil_pressure = std::max(0.0,   g_state.oil_pressure);
        g_state.cpu_usage    = std::min(100.0, std::max(0.0, g_state.cpu_usage));
        g_state.memory_usage = std::min(100.0, std::max(0.0, g_state.memory_usage));

        // Derive sensor status from combined health
        if (g_state.engine_temp > 260 || g_state.oil_pressure < 10) {
            g_state.sensor_status = "FAILED";
        } else if (g_state.engine_temp > 220 || g_state.vibration > 0.75 ||
                   g_state.oil_pressure < 25) {
            g_state.sensor_status = "DEGRADED";
        } else {
            g_state.sensor_status = "OK";
        }

        g_state.timestamp = utc_now();

        // Output telemetry to stdout as JSON — this is the mock-mode wire
        // format consumed by the Python corba_bridge when TAO is not available.
        std::cout << "{"
            << "\"engine_temp\":"  << std::fixed << std::setprecision(2) << g_state.engine_temp  << ","
            << "\"vibration\":"    << g_state.vibration    << ","
            << "\"fuel_flow\":"    << g_state.fuel_flow     << ","
            << "\"oil_pressure\":" << g_state.oil_pressure  << ","
            << "\"cpu_usage\":"    << g_state.cpu_usage     << ","
            << "\"memory_usage\":" << g_state.memory_usage  << ","
            << "\"sensor_status\":\"" << g_state.sensor_status << "\","
            << "\"timestamp\":\""  << g_state.timestamp     << "\""
            << "}" << std::endl;
    }
}

/* -----------------------------------------------------------------------
 * TAO CORBA servant (compiled only when TAO headers are present)
 * --------------------------------------------------------------------- */
#ifdef USE_TAO_ORB

class TelemetryService_impl : public POA_MissionSystem::TelemetryService {
public:
    MissionSystem::TelemetryData* getLatestTelemetry() override {
        std::lock_guard<std::mutex> lock(g_mutex);
        auto* td = new MissionSystem::TelemetryData();
        td->engine_temp   = g_state.engine_temp;
        td->vibration     = g_state.vibration;
        td->fuel_flow     = g_state.fuel_flow;
        td->oil_pressure  = g_state.oil_pressure;
        td->cpu_usage     = g_state.cpu_usage;
        td->memory_usage  = g_state.memory_usage;
        td->sensor_status = (g_state.sensor_status == "FAILED")   ?
                            MissionSystem::SENSOR_FAILED :
                            (g_state.sensor_status == "DEGRADED") ?
                            MissionSystem::SENSOR_DEGRADED :
                            MissionSystem::SENSOR_OK;
        td->timestamp = CORBA::string_dup(g_state.timestamp.c_str());
        return td;
    }

    CORBA::Boolean ping() override { return true; }
};

int tao_main(int argc, char* argv[]) {
    try {
        CORBA::ORB_var orb = CORBA::ORB_init(argc, argv, "TAO");

        CORBA::Object_var poa_obj =
            orb->resolve_initial_references("RootPOA");
        PortableServer::POA_var poa =
            PortableServer::POA::_narrow(poa_obj.in());
        PortableServer::POAManager_var mgr = poa->the_POAManager();
        mgr->activate();

        TelemetryService_impl* servant = new TelemetryService_impl();
        PortableServer::ObjectId_var oid =
            poa->activate_object(servant);

        CORBA::Object_var ref = poa->id_to_reference(oid.in());
        CORBA::String_var ior = orb->object_to_string(ref.in());

        // Write IOR to file so client can locate the service
        FILE* fp = fopen("/tmp/TelemetryService.ior", "w");
        if (fp) { fputs(ior.in(), fp); fclose(fp); }

        std::cerr << "[TAO] TelemetryService IOR written to /tmp/TelemetryService.ior" << std::endl;
        std::cerr << "[TAO] Server running — press Ctrl-C to stop" << std::endl;

        // Start simulation thread
        std::thread sim_thread(simulation_thread);
        sim_thread.detach();

        orb->run();
        orb->destroy();
    } catch (const CORBA::Exception& e) {
        std::cerr << "[TAO] CORBA exception: " << e._info().c_str() << std::endl;
        return 1;
    }
    return 0;
}
#endif  // USE_TAO_ORB

/* -----------------------------------------------------------------------
 * Mock/fallback main — runs without TAO, outputs JSON to stdout
 * --------------------------------------------------------------------- */
int main(int argc, char* argv[]) {
#ifdef USE_TAO_ORB
    return tao_main(argc, argv);
#else
    std::cerr << "[MOCK] Legacy CORBA Telemetry Server (mock mode)" << std::endl;
    std::cerr << "[MOCK] Streaming JSON telemetry to stdout every 1s" << std::endl;
    std::cerr << "[MOCK] Write /tmp/missionforge_fault to inject fault" << std::endl;
    std::cerr << "[MOCK] Write /tmp/missionforge_reset to reset" << std::endl;

    // Initialize timestamp
    g_state.timestamp = utc_now();

    // Run simulation inline (stdout loop)
    simulation_thread();
    return 0;
#endif
}
