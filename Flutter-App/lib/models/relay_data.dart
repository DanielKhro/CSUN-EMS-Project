class RelayData {
  final int mode;
  final bool relay1;
  final bool relay2;
  final bool relay3;

  const RelayData({
    required this.mode,
    required this.relay1,
    required this.relay2,
    required this.relay3,
  });

  String get modeName {
    switch (mode) {
      case 0:
        return 'Auto';
      case 1:
        return 'Battery';
      case 2:
        return 'Grid';
      default:
        return 'Unknown';
    }
  }
}