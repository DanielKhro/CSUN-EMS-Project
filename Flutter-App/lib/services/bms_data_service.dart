import '../models/bms_data.dart';

class BmsDataService {
  Future<BmsData> getBmsData() async {
    await Future.delayed(const Duration(milliseconds: 300));

    return const BmsData(
      stateOfCharge: 87.5,
      stateOfHealth: 98.0,
      batteryVoltage: 51.8,
      batteryCurrent: -12.4,
      batteryTemperature: 29.5,
    );
  }
}