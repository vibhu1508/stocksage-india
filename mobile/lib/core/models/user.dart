class User {
  final int id;
  final String email;
  final String name;
  final String? picture;
  final bool isAdmin;

  User({
    required this.id,
    required this.email,
    required this.name,
    this.picture,
    this.isAdmin = false,
  });

  factory User.fromJson(Map<String, dynamic> json) {
    return User(
      id: json['id'],
      email: json['email'],
      name: json['name'] ?? '',
      picture: json['picture'],
      isAdmin: json['is_admin'] ?? false,
    );
  }
}
