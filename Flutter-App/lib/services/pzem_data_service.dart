import '../models/pzem_data.dart';

/// Supplies PZEM measurement data to the Flutter application.
///
/// This version returns placeholder values so the user interface can be
/// developed and tested before connecting to the Raspberry Pi backend.
class PzemDataService {
  /// Returns one set of simulated Grid and Load PZEM measurements.
  Future<PzemData> getPzemData() async {
    // Simulates a small delay, similar to receiving data over a network.
    await Future.delayed(
      const Duration(milliseconds: 300),
    );

    return const PzemData(
      // Grid PZEM measurements
      gridVoltage: 120.4,
      gridCurrent: 4.2,
      gridPower: 485.0,
      gridEnergy: 15420.0,
      gridFrequency: 60.0,
      gridPowerFactor: 0.96,
      gridAlarmStatus: 0,

      // Load PZEM measurements
      loadVoltage: 119.8,
      loadCurrent: 3.5,
      loadPower: 402.0,
      loadEnergy: 12100.0,
      loadFrequency: 60.0,
      loadPowerFactor: 0.94,
      loadAlarmStatus: 0,
    );
  }
}