class User {
  final int id;
  final String email;
  final String name;
  final String? picture;
  final bool isAdmin;
  final String? phone;
  final String? address;
  final String? occupation;
  final String? tradingExperience;
  final bool onboardingCompleted;
  final bool onboardingSkipped;

  User({
    required this.id,
    required this.email,
    required this.name,
    this.picture,
    this.isAdmin = false,
    this.phone,
    this.address,
    this.occupation,
    this.tradingExperience,
    this.onboardingCompleted = false,
    this.onboardingSkipped = false,
  });

  factory User.fromJson(Map<String, dynamic> json) {
    return User(
      id: json['id'],
      email: json['email'],
      name: json['name'] ?? '',
      picture: json['picture'],
      isAdmin: json['is_admin'] ?? false,
      phone: json['phone'],
      address: json['address'],
      occupation: json['occupation'],
      tradingExperience: json['trading_experience'],
      onboardingCompleted: json['onboarding_completed'] ?? false,
      onboardingSkipped: json['onboarding_skipped'] ?? false,
    );
  }
}
