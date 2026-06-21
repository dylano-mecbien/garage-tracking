from django.urls import path
from rest_framework.routers import DefaultRouter
from rest_framework import serializers, viewsets
from rest_framework.permissions import IsAuthenticated
from .models import Vehicule, Client, Conducteur

class ClientSerializer(serializers.ModelSerializer):
    class Meta:
        model = Client
        fields = '__all__'

class VehiculeSerializer(serializers.ModelSerializer):
    client_nom = serializers.CharField(source='client.__str__', read_only=True)
    class Meta:
        model = Vehicule
        fields = '__all__'

class ConducteurSerializer(serializers.ModelSerializer):
    class Meta:
        model = Conducteur
        fields = '__all__'

class ClientViewSet(viewsets.ModelViewSet):
    queryset = Client.objects.filter(is_active=True).order_by('nom')
    serializer_class = ClientSerializer
    permission_classes = [IsAuthenticated]
    search_fields = ['nom', 'prenom', 'telephone', 'numero_client']

class VehiculeViewSet(viewsets.ModelViewSet):
    queryset = Vehicule.objects.select_related('client').filter(is_active=True).order_by('immatriculation')
    serializer_class = VehiculeSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ['marque', 'type_carburant']
    search_fields = ['immatriculation', 'marque', 'modele', 'numero_chassis']

class ConducteurViewSet(viewsets.ModelViewSet):
    queryset = Conducteur.objects.order_by('nom')
    serializer_class = ConducteurSerializer
    permission_classes = [IsAuthenticated]
    search_fields = ['nom', 'prenom', 'telephone', 'cni']

router = DefaultRouter()
router.register('clients', ClientViewSet)
router.register('vehicules', VehiculeViewSet)
router.register('conducteurs', ConducteurViewSet)
urlpatterns = router.urls
