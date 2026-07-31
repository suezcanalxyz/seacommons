#include "SeaCommonsRaft.h"

#include "BuoyancyComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/CollisionProfile.h"
#include "UObject/ConstructorHelpers.h"

ASeaCommonsRaft::ASeaCommonsRaft()
{
    PrimaryActorTick.bCanEverTick = false;
    Tags.Add(TEXT("SeaCommonsGenerated"));
    Tags.Add(TEXT("AnonymousVessel"));

    Hull = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Hull"));
    SetRootComponent(Hull);
    Hull->SetMobility(EComponentMobility::Movable);
    Hull->SetCollisionProfileName(UCollisionProfile::PhysicsActor_ProfileName);
    Hull->SetSimulatePhysics(true);
    Hull->SetEnableGravity(true);
    Hull->SetLinearDamping(0.35f);
    Hull->SetAngularDamping(1.35f);
    Hull->SetRelativeScale3D(FVector(13.0f, 4.2f, 1.15f));

    static ConstructorHelpers::FObjectFinder<UStaticMesh> CubeMesh(
        TEXT("/Engine/BasicShapes/Cube.Cube")
    );
    if (CubeMesh.Succeeded())
    {
        Hull->SetStaticMesh(CubeMesh.Object);
    }

    Cabin = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Cabin"));
    Cabin->SetupAttachment(Hull);
    Cabin->SetCollisionEnabled(ECollisionEnabled::NoCollision);
    Cabin->SetRelativeLocation(FVector(-180.0f, 0.0f, 115.0f));
    Cabin->SetRelativeScale3D(FVector(0.28f, 0.68f, 1.65f));
    if (CubeMesh.Succeeded())
    {
        Cabin->SetStaticMesh(CubeMesh.Object);
    }

    Buoyancy = CreateDefaultSubobject<UBuoyancyComponent>(TEXT("Buoyancy"));
    Buoyancy->AddCustomPontoon(105.0f, FVector(420.0f, -135.0f, -45.0f));
    Buoyancy->AddCustomPontoon(105.0f, FVector(420.0f, 135.0f, -45.0f));
    Buoyancy->AddCustomPontoon(115.0f, FVector(-420.0f, -135.0f, -45.0f));
    Buoyancy->AddCustomPontoon(115.0f, FVector(-420.0f, 135.0f, -45.0f));
    Buoyancy->BuoyancyData.BuoyancyCoefficient = 1.15f;
    Buoyancy->BuoyancyData.BuoyancyDamp = 2.4f;
    Buoyancy->BuoyancyData.BuoyancyDamp2 = 0.35f;
    Buoyancy->BuoyancyData.bApplyDragForcesInWater = true;
    Buoyancy->BuoyancyData.DragCoefficient = 28.0f;
    Buoyancy->BuoyancyData.DragCoefficient2 = 0.015f;
    Buoyancy->BuoyancyData.AngularDragCoefficient = 1.6f;
}

void ASeaCommonsRaft::BeginPlay()
{
    Super::BeginPlay();
    Hull->SetMassOverrideInKg(NAME_None, 6500.0f, true);
}
