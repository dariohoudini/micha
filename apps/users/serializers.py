from rest_framework import serializers
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.contrib.auth import authenticate
User = get_user_model()


# ---------------------------
# User Registration Serializer
# ---------------------------
class UserRegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = [
            'id', 'email', 'password',
            'full_name', 'phone', 'city',
            'latitude', 'longitude',
            'is_seller', 'is_verified_seller'
        ]

    def create(self, validated_data):
        password = validated_data.pop('password')
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user


# ---------------------------
# User Profile Serializer
# ---------------------------
class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            'id', 'email',
            'full_name', 'phone', 'city',
            'latitude', 'longitude',
            'is_seller', 'is_verified_seller'
        ]
        read_only_fields = ['id', 'is_verified_seller']


# ---------------------------
# JWT Token Serializer
# ---------------------------
class MyTokenObtainPairSerializer(TokenObtainPairSerializer):
    username_field = 'email'  # Make email the login field

    def validate(self, attrs):
        # Use authenticate() with email
        email = attrs.get("email")
        password = attrs.get("password")

        user = authenticate(self.context['request'], email=email, password=password)
        if not user:
            raise serializers.ValidationError("No active account found with the given credentials")

        # Call super to get token
        data = super().get_token(user)
        data['email'] = user.email
        data['is_seller'] = getattr(user, 'is_seller', False)
        return {
            'refresh': str(data),
            'access': str(data.access_token)
        }