import '../models/relay_data.dart';

class RelayService {
  int _currentMode = 0;

  Future<RelayData> getRelayData() async {
    await Future.delayed(
      const Duration(milliseconds: 300),
    );

    return RelayData(
      mode: _currentMode,
      relay1: _currentMode == 1,
      relay2: _currentMode == 2,
      relay3: _currentMode == 0,
    );
  }

  Future<RelayData> setRelayMode(int mode) async {
    if (mode < 0 || mode > 2) {
      throw ArgumentError(
        'Relay mode must be 0, 1, or 2.',
      );
    }

    await Future.delayed(
      const Duration(milliseconds: 300),
    );

    _currentMode = mode;

    return getRelayData();
  }
}